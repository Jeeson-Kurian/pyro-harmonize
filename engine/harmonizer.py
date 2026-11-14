"""
Cross-sensor harmonisation with held-out validation.

Target scale: Aqua MODIS. Every other platform is converted to "what Aqua MODIS
would have reported", because (a) a coarse sensor cannot be upgraded to see the
small fires it missed, but a fine sensor can be degraded to the coarse one, and
(b) Aqua shares the early-afternoon orbit with every VIIRS platform.

For one target platform (for example NOAA-20 VIIRS), using the cells and
half-days observed by both platforms:

    E[ Aqua active cells ]  =  (1 + rho) * sum over target-active cells of  p(x)
    E[ Aqua FRP ]           =  (1 + rho_frp) * sum of  p(x) * g(x)

    p(x)    probability that Aqua also reports the cell, given the target's FRP,
            pixel count and day/night            (logistic regression)
    g(x)    expected Aqua FRP of the cell when both report it
            (log-log regression with Duan smearing; plain or ridge)
    rho     Aqua-active cells the target did not report, relative to shared cells

Nothing here is trusted until it has been tested on data that were not used
for fitting. Each candidate, including the do-nothing and constant-ratio
baselines, is scored on held-out years (grouped K-fold) and again on a
forward-in-time split. The simplest method whose held-out error is within 2 %
of the best is the one applied. If a baseline wins, the baseline is used.

There are no fallback numbers. If the overlap is too small to fit AND validate,
the platform is reported as "not calibrated" and is left out of the harmonised
record.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .matching import pair_summary

COUNT_METHODS = ["gridded_cells", "ratio_scaled", "detection_model"]   # simplest first
FRP_METHODS = ["unscaled", "ratio_scaled", "loglinear", "ridge"]       # simplest first
METHOD_LABELS = {
    "raw_hotspots": "Raw hot-spot counts (no harmonisation)",
    "gridded_cells": "Common grid only (no calibration)",
    "ratio_scaled": "Common grid + one constant ratio",
    "detection_model": "Common grid + detection-probability model",
    "unscaled": "Target FRP as reported (no calibration)",
    "loglinear": "Detection model x log-log FRP regression",
    "ridge": "Detection model x ridge FRP regression",
}

MIN_TARGET_ACTIVE = 200
MIN_BOTH_ACTIVE = 50
MIN_MONTHS = 6
MIN_FRP_PAIRS = 30
PREFER_SIMPLER_WITHIN = 0.02


# --------------------------------------------------------------------------- fitting

def _count_features(rows: pd.DataFrame, frp_fill: float) -> np.ndarray:
    frp = rows["t_frp"].fillna(frp_fill).clip(lower=1e-3).values
    return np.column_stack([np.log10(frp), np.log10(np.maximum(rows["t_npix"].values, 1)),
                            (rows["slot"].values == "night").astype(float)])


def _frp_features(rows: pd.DataFrame, frp_fill: float, scan_fill: float) -> np.ndarray:
    base = _count_features(rows, frp_fill)
    scan = rows["t_scan"].fillna(scan_fill).values
    return np.column_stack([base, scan])


def _slot_ratio(numerator: np.ndarray, denominator: np.ndarray, night: np.ndarray,
                min_denominator: float) -> Dict[str, float]:
    """numerator.sum()/denominator.sum() per slot; pooled value where a slot is too thin."""
    total = float(denominator.sum())
    pooled = float(numerator.sum() / total) if total > 0 else 0.0
    out = {}
    for slot, mask in (("day", ~night), ("night", night)):
        d = float(denominator[mask].sum())
        out[slot] = float(numerator[mask].sum() / d) if d > 0 and d >= min_denominator else pooled
    return out


def fit_methods(train: pd.DataFrame) -> Dict[str, Any]:
    """Fit every candidate on one training set of pairs."""
    t_rows = train[train["t_active"]]
    both = train["t_active"] & train["r_active"]
    r_only = ~train["t_active"] & train["r_active"]
    fit: Dict[str, Any] = {}
    valid_frp = t_rows["t_frp"].dropna()
    fit["frp_fill"] = float(valid_frp.median()) if len(valid_frp) else 1.0
    scan = t_rows["t_scan"].dropna()
    fit["scan_fill"] = float(scan.median()) if len(scan) else 1.0

    n_t = int(len(t_rows))
    n_r = int(train["r_active"].sum())
    fit["k_cells"] = n_r / n_t if n_t else np.nan
    sum_t_frp = float(t_rows["t_frp"].fillna(fit["frp_fill"]).sum())
    sum_r_frp = float(train.loc[train["r_active"], "r_frp"].sum(skipna=True))
    fit["k_frp"] = sum_r_frp / sum_t_frp if sum_t_frp > 0 else np.nan

    night = (train["slot"] == "night").values
    both_v, r_only_v = both.values, r_only.values
    fit["rho_count"] = _slot_ratio(r_only_v.astype(float), both_v.astype(float), night, MIN_FRP_PAIRS)
    r_frp = train["r_frp"].fillna(0.0).values
    fit["rho_frp"] = _slot_ratio(r_frp * r_only_v, r_frp * both_v, night, 1e-9)

    # detection probability
    y = t_rows["r_active"].values.astype(int)
    fit["detect"] = None
    fit["base_rate"] = float(y.mean()) if len(y) else 0.0
    if len(y) >= 50 and 0 < y.sum() < len(y):
        model = make_pipeline(StandardScaler(), LogisticRegression(C=10.0, max_iter=1000))
        model.fit(_count_features(t_rows, fit["frp_fill"]), y)
        fit["detect"] = model

    # FRP given both active
    pairs = train[both & train["t_frp"].notna() & train["r_frp"].notna()
                  & (train["t_frp"] > 0) & (train["r_frp"] > 0)]
    fit["frp_ols"] = fit["frp_ridge"] = None
    fit["n_frp_pairs"] = int(len(pairs))
    if len(pairs) >= MIN_FRP_PAIRS:
        log_r = np.log(pairs["r_frp"].values)
        x_ols = np.log(pairs["t_frp"].values).reshape(-1, 1)
        ols = LinearRegression().fit(x_ols, log_r)
        fit["frp_ols"] = ols
        fit["smear_ols"] = float(np.mean(np.exp(log_r - ols.predict(x_ols))))
        x_ridge = _frp_features(pairs, fit["frp_fill"], fit["scan_fill"])
        ridge = make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(x_ridge, log_r)
        fit["frp_ridge"] = ridge
        fit["smear_ridge"] = float(np.mean(np.exp(log_r - ridge.predict(x_ridge))))
    return fit


def predict_rows(fit: Dict[str, Any], rows: pd.DataFrame) -> pd.DataFrame:
    """
    Reference-equivalent contribution of each target-active (cell, half-day),
    under every candidate. rows needs t_npix, t_frp, t_scan, slot.
    """
    out = pd.DataFrame(index=rows.index)
    n = len(rows)
    night = rows["slot"].values == "night"
    t_frp = rows["t_frp"].fillna(fit["frp_fill"]).values
    if fit["detect"] is not None and n:
        p = fit["detect"].predict_proba(_count_features(rows, fit["frp_fill"]))[:, 1]
    else:
        p = np.full(n, fit["base_rate"])
    rho_c = np.where(night, fit["rho_count"]["night"], fit["rho_count"]["day"])
    rho_f = np.where(night, fit["rho_frp"]["night"], fit["rho_frp"]["day"])
    out["p_detect"] = p
    out["c_gridded_cells"] = 1.0
    out["c_ratio_scaled"] = fit["k_cells"]
    out["c_detection_model"] = (1.0 + rho_c) * p
    out["f_unscaled"] = t_frp
    out["f_ratio_scaled"] = fit["k_frp"] * t_frp
    if fit["frp_ols"] is not None and n:
        g = fit["smear_ols"] * np.exp(fit["frp_ols"].predict(np.log(np.clip(t_frp, 1e-3, None)).reshape(-1, 1)))
        out["f_loglinear"] = (1.0 + rho_f) * p * g
        g2 = fit["smear_ridge"] * np.exp(
            fit["frp_ridge"].predict(_frp_features(rows, fit["frp_fill"], fit["scan_fill"])))
        out["f_ridge"] = (1.0 + rho_f) * p * g2
    return out


# ------------------------------------------------------------------------ validation

def _score(pred: np.ndarray, obs: np.ndarray, kind: str) -> Dict[str, Any]:
    """Agreement of monthly totals. kind = 'count' or 'frp'."""
    pred = np.asarray(pred, dtype=float)
    obs = np.asarray(obs, dtype=float)
    if len(obs) == 0 or not np.isfinite(pred).all():
        return {"available": False}
    if kind == "count":
        scaled = np.sqrt(np.clip(pred, 0, None)) - np.sqrt(obs)
        scale = "sqrt"
        floor = 5.0
    else:
        scaled = np.log1p(np.clip(pred, 0, None)) - np.log1p(obs)
        scale = "log1p"
        floor = 0.0
    big = obs > floor
    result = {
        "available": True,
        "months": int(len(obs)),
        "observed_total": round(float(obs.sum()), 1),
        "predicted_total": round(float(pred.sum()), 1),
        "total_bias_pct": round(float(100.0 * (pred.sum() - obs.sum()) / obs.sum()), 1) if obs.sum() > 0 else None,
        "rmse": round(float(np.sqrt(np.mean((pred - obs) ** 2))), 2),
        "scaled_rmse": round(float(np.sqrt(np.mean(scaled ** 2))), 4),
        "scale": scale,
        "median_abs_pct_error": round(float(np.median(100.0 * np.abs(pred[big] - obs[big]) / obs[big])), 1)
        if big.any() else None,
        "spearman_r": None,
    }
    if len(obs) >= 4 and np.std(pred) > 0 and np.std(obs) > 0:
        rho, _ = stats.spearmanr(pred, obs)
        result["spearman_r"] = round(float(rho), 3)
    return result


def _monthly(test: pd.DataFrame, pred: pd.DataFrame) -> pd.DataFrame:
    """Monthly observed reference totals and predicted totals for one test set."""
    obs = test.groupby("month").agg(
        obs_cells=("r_active", "sum"),
        obs_frp=("r_frp", lambda s: float(s.sum(skipna=True))),
        obs_ref_hotspots=("r_npix", "sum"),
        raw_target_hotspots=("t_npix", "sum"),
    )
    t_rows = test[test["t_active"]]
    summed = pred.loc[t_rows.index].assign(month=t_rows["month"].values).groupby("month").sum(min_count=1)
    monthly = obs.join(summed.drop(columns=["p_detect"], errors="ignore"), how="left").fillna(
        {c: 0.0 for c in summed.columns})
    return monthly


def _score_all(monthly: pd.DataFrame) -> Dict[str, Any]:
    scores = {"count": {}, "frp": {}}
    scores["count"]["raw_hotspots"] = _score(monthly["raw_target_hotspots"].values,
                                             monthly["obs_ref_hotspots"].values, "count")
    for m in COUNT_METHODS:
        scores["count"][m] = _score(monthly[f"c_{m}"].values, monthly["obs_cells"].values, "count")
    for m in FRP_METHODS:
        col = f"f_{m}"
        scores["frp"][m] = (_score(monthly[col].values, monthly["obs_frp"].values, "frp")
                            if col in monthly and monthly[col].notna().all() else {"available": False})
    return scores


def _select(scores: Dict[str, Any], order: List[str]) -> Optional[str]:
    """Simplest method unless a more complex one is clearly better on held-out data."""
    chosen = None
    for method in order:
        s = scores.get(method, {})
        if not s.get("available"):
            continue
        if chosen is None or s["scaled_rmse"] < (1.0 - PREFER_SIMPLER_WITHIN) * scores[chosen]["scaled_rmse"]:
            chosen = method
    return chosen


class TargetCalibration:
    """Calibration of one target platform onto the reference platform."""

    def __init__(self, target: str, reference: str):
        self.target = target
        self.reference = reference
        self.status = "not_calibrated"
        self.reason = ""
        self.fit: Optional[Dict[str, Any]] = None
        self.count_method: Optional[str] = None
        self.frp_method: Optional[str] = None
        self.summary: Dict[str, Any] = {}
        self.cv_scores: Dict[str, Any] = {}
        self.forward_scores: Optional[Dict[str, Any]] = None
        self.cv_monthly: Optional[pd.DataFrame] = None
        self.interval: Dict[str, Any] = {"count": None, "frp": None}
        self.validation_design = ""
        self.diagnostics: Dict[str, Any] = {}

    # -- fit + validate ---------------------------------------------------------
    def fit_validate(self, pairs: pd.DataFrame) -> "TargetCalibration":
        self.summary = pair_summary(pairs) if len(pairs) else {}
        n_t = int(pairs["t_active"].sum()) if len(pairs) else 0
        n_both = int((pairs["t_active"] & pairs["r_active"]).sum()) if len(pairs) else 0
        n_months = int(pairs["month"].nunique()) if len(pairs) else 0
        problems = []
        if n_t < MIN_TARGET_ACTIVE:
            problems.append(f"only {n_t} target-active cell half-days in the overlap (need {MIN_TARGET_ACTIVE})")
        if n_both < MIN_BOTH_ACTIVE:
            problems.append(f"only {n_both} cells seen by both platforms (need {MIN_BOTH_ACTIVE})")
        if n_months < MIN_MONTHS:
            problems.append(f"only {n_months} overlap months (need {MIN_MONTHS})")
        if problems:
            self.reason = "; ".join(problems)
            return self

        n_years = int(pairs["year"].nunique())
        if n_years >= 3:
            groups = pairs["year"].values
            self.validation_design = f"leave-years-out, {min(5, n_years)} folds over {n_years} years"
        else:
            groups = pairs["month"].values
            self.validation_design = (f"leave-months-out, {min(5, n_months)} folds over {n_months} months "
                                      "(fewer than 3 overlap years: weaker test)")
        n_groups = len(np.unique(groups))
        folds = GroupKFold(n_splits=min(5, n_groups))
        monthly_parts = []
        for train_idx, test_idx in folds.split(pairs, groups=groups):
            train, test = pairs.iloc[train_idx], pairs.iloc[test_idx]
            if not train["t_active"].any() or not test["t_active"].any():
                continue
            fold_fit = fit_methods(train)
            pred = predict_rows(fold_fit, test[test["t_active"]])
            monthly_parts.append(_monthly(test, pred))
        if not monthly_parts:
            self.reason = "cross-validation produced no usable folds"
            return self
        # a month belongs to exactly one fold; min_count keeps "method unavailable" as NaN
        monthly = pd.concat(monthly_parts).groupby(level=0).sum(min_count=1).sort_index()
        self.cv_monthly = monthly
        self.cv_scores = _score_all(monthly)

        # forward-in-time test: fit on the earliest ~70 % of periods, test on the rest
        ordered = np.sort(np.unique(groups))
        cut = int(np.ceil(0.7 * len(ordered)))
        if 2 <= cut < len(ordered):
            train = pairs[np.isin(groups, ordered[:cut])]
            test = pairs[np.isin(groups, ordered[cut:])]
            if train["t_active"].sum() >= MIN_TARGET_ACTIVE and test["t_active"].any():
                pred = predict_rows(fit_methods(train), test[test["t_active"]])
                self.forward_scores = _score_all(_monthly(test, pred))
                self.forward_scores["train_periods"] = [str(ordered[0]), str(ordered[cut - 1])]
                self.forward_scores["test_periods"] = [str(ordered[cut]), str(ordered[-1])]

        self.count_method = _select(self.cv_scores["count"], COUNT_METHODS)
        self.frp_method = _select(self.cv_scores["frp"], FRP_METHODS)
        if self.count_method is None:
            self.reason = "no count method could be validated"
            return self

        # empirical 90 % interval for monthly totals, from out-of-fold errors
        if len(monthly) >= 12:
            r = np.sqrt(monthly["obs_cells"].values) - np.sqrt(np.clip(monthly[f"c_{self.count_method}"].values, 0, None))
            self.interval["count"] = {"scale": "sqrt", "q05": float(np.quantile(r, 0.05)),
                                      "q95": float(np.quantile(r, 0.95)), "months": int(len(monthly))}
            if self.frp_method:
                r = np.log1p(monthly["obs_frp"].values) - np.log1p(np.clip(monthly[f"f_{self.frp_method}"].values, 0, None))
                self.interval["frp"] = {"scale": "log1p", "q05": float(np.quantile(r, 0.05)),
                                        "q95": float(np.quantile(r, 0.95)), "months": int(len(monthly))}

        self.fit = fit_methods(pairs)   # final fit on the whole overlap
        self.status = "calibrated"
        self.diagnostics = self._diagnostics(pairs)
        return self

    # -- apply ------------------------------------------------------------------
    def apply(self, target_cells: pd.DataFrame) -> pd.DataFrame:
        """Reference-equivalent cells and FRP for every target-active (cell, half-day)."""
        rows = pd.DataFrame({
            "t_npix": target_cells["n_pixels"].values,
            "t_frp": target_cells["frp_mw"].values,
            "t_scan": target_cells["scan_km"].values,
            "slot": target_cells["slot"].values,
        }, index=target_cells.index)
        pred = predict_rows(self.fit, rows)
        out = pd.DataFrame(index=target_cells.index)
        out["eq_cells"] = pred[f"c_{self.count_method}"].values
        column = f"f_{self.frp_method}" if self.frp_method else None
        out["eq_frp_mw"] = pred[column].values if column in pred.columns else np.nan
        return out

    # -- reporting --------------------------------------------------------------
    def _diagnostics(self, pairs: pd.DataFrame) -> Dict[str, Any]:
        t_rows = pairs[pairs["t_active"] & pairs["t_frp"].notna() & (pairs["t_frp"] > 0)]
        diag: Dict[str, Any] = {}
        # empirical detection rate by target-FRP decile, with the fitted curve
        if len(t_rows) >= 100:
            edges = np.unique(np.quantile(t_rows["t_frp"], np.linspace(0, 1, 11)))
            if len(edges) > 2:
                bins = pd.cut(t_rows["t_frp"], edges, include_lowest=True)
                pred = predict_rows(self.fit, t_rows)["p_detect"]
                table = t_rows.assign(p=pred.values).groupby(bins, observed=True).agg(
                    frp=("t_frp", "median"), observed=("r_active", "mean"),
                    predicted=("p", "mean"), n=("r_active", "size"))
                diag["detection_by_frp"] = [
                    {"target_frp_mw": round(float(r.frp), 2), "observed_rate": round(float(r.observed), 3),
                     "model_rate": round(float(r.predicted), 3), "n": int(r.n)}
                    for r in table.itertuples()]
        both = pairs[pairs["t_active"] & pairs["r_active"] & pairs["t_frp"].notna()
                     & pairs["r_frp"].notna() & (pairs["t_frp"] > 0) & (pairs["r_frp"] > 0)]
        if len(both):
            sample = both.sample(min(len(both), 400), random_state=0)
            diag["frp_pairs_sample"] = [
                {"target_frp_mw": round(float(a), 2), "reference_frp_mw": round(float(b), 2),
                 "dt_min": None if pd.isna(c) else round(float(c), 1)}
                for a, b, c in zip(sample["t_frp"], sample["r_frp"], sample["dt_min"])]
            diag["frp_pairs_total"] = int(len(both))

            def loglog(frame):
                if len(frame) < MIN_FRP_PAIRS:
                    return None
                res = stats.linregress(np.log(frame["t_frp"]), np.log(frame["r_frp"]))
                return {"n": int(len(frame)), "slope": round(float(res.slope), 3),
                        "intercept": round(float(res.intercept), 3),
                        "r2": round(float(res.rvalue ** 2), 3)}
            # does the relationship change when only near-simultaneous pairs are used?
            diag["frp_fit_all_pairs"] = loglog(both)
            diag["frp_fit_within_15_min"] = loglog(both[both["dt_min"] <= 15])
        return diag

    def report(self) -> Dict[str, Any]:
        out = {
            "target": self.target, "reference": self.reference, "status": self.status,
            "reason": self.reason, "matching": self.summary,
            "validation_design": self.validation_design,
            "selected_count_method": self.count_method,
            "selected_frp_method": self.frp_method,
            "selection_rule": (f"simplest method whose held-out scaled RMSE is within "
                               f"{int(PREFER_SIMPLER_WITHIN * 100)} % of the best"),
            "cross_validation": self.cv_scores,
            "forward_in_time_test": self.forward_scores,
            "monthly_interval": self.interval,
            "method_labels": METHOD_LABELS,
            "diagnostics": self.diagnostics,
        }
        if self.fit is not None:
            params = {"k_cells": round(self.fit["k_cells"], 4),
                      "k_frp": None if not np.isfinite(self.fit["k_frp"]) else round(self.fit["k_frp"], 4),
                      "rho_count": {k: round(v, 4) for k, v in self.fit["rho_count"].items()},
                      "rho_frp": {k: round(v, 4) for k, v in self.fit["rho_frp"].items()},
                      "frp_pairs_used": self.fit["n_frp_pairs"]}
            if self.fit["detect"] is not None:
                lr = self.fit["detect"].named_steps["logisticregression"]
                params["detection_coefficients_standardised"] = {
                    "log10_frp": round(float(lr.coef_[0][0]), 3),
                    "log10_pixels": round(float(lr.coef_[0][1]), 3),
                    "night": round(float(lr.coef_[0][2]), 3),
                    "intercept": round(float(lr.intercept_[0]), 3)}
            if self.fit["frp_ols"] is not None:
                params["loglinear"] = {"slope": round(float(self.fit["frp_ols"].coef_[0]), 3),
                                       "intercept": round(float(self.fit["frp_ols"].intercept_), 3),
                                       "smearing_factor": round(self.fit["smear_ols"], 3)}
            out["fitted_parameters"] = params
        if self.cv_monthly is not None:
            m = self.cv_monthly
            cols = {"month": list(m.index), "observed_reference_cells": m["obs_cells"].round(1).tolist(),
                    "raw_target_hotspots": m["raw_target_hotspots"].round(1).tolist(),
                    "observed_reference_hotspots": m["obs_ref_hotspots"].round(1).tolist(),
                    "gridded_cells": m["c_gridded_cells"].round(1).tolist()}
            if self.count_method:
                cols["selected_count"] = m[f"c_{self.count_method}"].round(1).tolist()
            cols["observed_reference_frp"] = m["obs_frp"].round(1).tolist()
            if self.frp_method:
                cols["selected_frp"] = m[f"f_{self.frp_method}"].round(1).tolist()
            out["held_out_monthly"] = cols
        return out


def monthly_interval(values: np.ndarray, interval: Optional[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray]:
    """Apply the empirical held-out error band to monthly point estimates."""
    values = np.asarray(values, dtype=float)
    if interval is None:
        nan = np.full(len(values), np.nan)
        return nan, nan
    if interval["scale"] == "sqrt":
        root = np.sqrt(np.clip(values, 0, None))
        return np.clip(root + interval["q05"], 0, None) ** 2, (root + interval["q95"]) ** 2
    logv = np.log1p(np.clip(values, 0, None))
    return np.clip(np.expm1(logv + interval["q05"]), 0, None), np.expm1(logv + interval["q95"])
