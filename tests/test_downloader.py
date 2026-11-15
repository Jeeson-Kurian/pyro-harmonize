"""FIRMS downloader: request planning, error handling, caching, manifest. No network is used."""

import json
from datetime import date

import pytest

from data.download_nasa_firms import (FirmsError, download, merge_intervals, parse_firms_csv,
                                      plan_chunks)

HEADER = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight,type\n"
SECRET = "0123456789abcdef0123456789abcdef"


class FakeResponse:
    def __init__(self, status, text):
        self.status_code, self.text = status, text


class FakeSession:
    """Answers like FIRMS; `script` can inject failures for specific request numbers."""

    def __init__(self, script=None, availability=True):
        self.calls, self.script, self.availability = [], script or {}, availability

    def get(self, url, timeout=None):
        self.calls.append(url)
        if "/data_availability/" in url:
            if not self.availability:
                return FakeResponse(500, "error")
            return FakeResponse(200, "data_id,min_date,max_date\nVIIRS_SNPP_SP,2012-01-20,2026-07-31\n"
                                     "MODIS_SP,2000-11-01,2026-08-31\n")
        n = sum(1 for c in self.calls if "/area/csv/" in c)
        if n in self.script:
            return self.script[n]
        day = url.rstrip("/").split("/")[-1]
        return FakeResponse(200, HEADER + f"38.5,-121.7,330.1,0.4,0.4,{day},2110,N,VIIRS,n,2,290.0,5.5,D,0\n")


def test_chunks_cover_every_day_exactly_once():
    chunks = plan_chunks(date(2012, 1, 20), date(2012, 2, 3), 5)
    days = [first.toordinal() + k for first, n in chunks for k in range(n)]
    assert days == list(range(date(2012, 1, 20).toordinal(), date(2012, 2, 3).toordinal() + 1))
    assert all(1 <= n <= 5 for _, n in chunks)
    assert plan_chunks(date(2020, 1, 2), date(2020, 1, 1), 5) == []
    with pytest.raises(ValueError):
        plan_chunks(date(2020, 1, 1), date(2020, 1, 9), 11)      # FIRMS documents DAY_RANGE 1..10


def test_intervals_merge_only_when_contiguous():
    chunks = [(date(2020, 1, 1), 5), (date(2020, 1, 6), 5), (date(2020, 1, 16), 5)]
    assert merge_intervals(chunks) == [["2020-01-01", "2020-01-10"], ["2020-01-16", "2020-01-20"]]


def test_error_text_is_never_read_as_no_fire():
    with pytest.raises(FirmsError):
        parse_firms_csv("Invalid MAP_KEY.")
    with pytest.raises(FirmsError):
        parse_firms_csv("")
    assert len(parse_firms_csv(HEADER)) == 0                     # a header alone is a valid empty answer


def test_download_writes_data_and_manifest_without_the_key(tmp_path):
    session = FakeSession()
    logs = []
    manifest = download((-124, 36, -119, 41), date(2020, 8, 1), date(2020, 8, 12), ["VIIRS_SNPP_SP"],
                        str(tmp_path), SECRET, chunk_days=5, pause=0, backoff=0, session=session,
                        log=logs.append)
    entry = manifest["sources"]["VIIRS_SNPP_SP"]
    assert entry["coverage"] == [["2020-08-01", "2020-08-12"]] and entry["failed_chunks"] == []
    assert entry["rows"] == 3
    assert (tmp_path / "VIIRS_SNPP_SP.csv").exists()
    area_calls = [c for c in session.calls if "/area/csv/" in c]
    assert [c.split("/")[-2] for c in area_calls] == ["5", "5", "2"]
    assert all("/VIIRS_SNPP_SP/-124,36,-119,41/" in c for c in area_calls)
    saved = (tmp_path / "manifest.json").read_text()
    assert SECRET not in saved and SECRET not in " ".join(logs)
    assert json.loads(saved)["synthetic"] is False


def test_failed_chunk_is_a_gap_not_a_zero_and_cache_is_reused(tmp_path):
    bad = {2: FakeResponse(200, "Invalid day range.")}
    session = FakeSession(script=bad)
    manifest = download((-124, 36, -119, 41), date(2020, 8, 1), date(2020, 8, 15), ["VIIRS_SNPP_SP"],
                        str(tmp_path), SECRET, pause=0, backoff=0, session=session, log=lambda *_: None)
    entry = manifest["sources"]["VIIRS_SNPP_SP"]
    assert entry["coverage"] == [["2020-08-01", "2020-08-05"], ["2020-08-11", "2020-08-15"]]
    assert entry["failed_chunks"][0]["start"] == "2020-08-06"
    assert SECRET not in json.dumps(manifest)
    # second run: only the failed chunk is requested again
    again = FakeSession()
    manifest = download((-124, 36, -119, 41), date(2020, 8, 1), date(2020, 8, 15), ["VIIRS_SNPP_SP"],
                        str(tmp_path), SECRET, pause=0, backoff=0, session=again, log=lambda *_: None)
    assert len([c for c in again.calls if "/area/csv/" in c]) == 1
    assert manifest["sources"]["VIIRS_SNPP_SP"]["coverage"] == [["2020-08-01", "2020-08-15"]]


def test_server_errors_are_retried(tmp_path):
    session = FakeSession(script={1: FakeResponse(503, "busy")})
    manifest = download((-124, 36, -119, 41), date(2020, 8, 1), date(2020, 8, 5), ["VIIRS_SNPP_SP"],
                        str(tmp_path), SECRET, pause=0, backoff=0, session=session, log=lambda *_: None)
    assert manifest["sources"]["VIIRS_SNPP_SP"]["failed_chunks"] == []


def test_transaction_limit_waits_instead_of_failing(tmp_path):
    session = FakeSession(script={1: FakeResponse(200, "Exceeding allowed transaction limit.")})
    manifest = download((-124, 36, -119, 41), date(2020, 8, 1), date(2020, 8, 5), ["VIIRS_SNPP_SP"],
                        str(tmp_path), SECRET, pause=0, backoff=0, limit_wait=0, session=session,
                        log=lambda *_: None)
    assert manifest["sources"]["VIIRS_SNPP_SP"]["failed_chunks"] == []


def test_dates_are_clipped_to_what_firms_holds(tmp_path):
    session = FakeSession()
    manifest = download((-124, 36, -119, 41), date(2012, 1, 1), date(2012, 1, 24), ["VIIRS_SNPP_SP"],
                        str(tmp_path), SECRET, pause=0, backoff=0, session=session, log=lambda *_: None)
    assert manifest["sources"]["VIIRS_SNPP_SP"]["coverage"] == [["2012-01-20", "2012-01-24"]]


def test_unknown_availability_never_extends_coverage_past_the_last_detection(tmp_path):
    empty_tail = {3: FakeResponse(200, HEADER), 4: FakeResponse(200, HEADER)}
    session = FakeSession(script=empty_tail, availability=False)
    manifest = download((-124, 36, -119, 41), date(2020, 8, 1), date(2020, 8, 20), ["VIIRS_SNPP_SP"],
                        str(tmp_path), SECRET, pause=0, backoff=0, retries=0, session=session,
                        log=lambda *_: None)
    entry = manifest["sources"]["VIIRS_SNPP_SP"]
    assert entry["availability_unknown"] is True
    assert entry["coverage"] == [["2020-08-01", "2020-08-06"]]


def test_one_command_pipeline_end_to_end_and_readme_block(tmp_path, monkeypatch):
    """
    make_submission flow without network: a fake FIRMS server serves simulated detections,
    the files are read back from disk like real ones, and the README block is built.
    The README of the repository itself is never touched by this test.
    """
    import pandas as pd
    from engine.pipeline import AnalysisConfig, run_analysis, load_dataset
    from engine.synthetic import generate_synthetic_firms
    from scripts.run_case_study import README_END, README_START, readme_block, update_readme

    world = generate_synthetic_firms(start="2018-04-01", end="2021-12-31", seed=21, aqua_outage=None)

    class WorldSession:
        def __init__(self):
            self.calls = 0

        def get(self, url, timeout=None):
            if "/data_availability/" in url:
                return FakeResponse(200, "data_id,min_date,max_date\n" + "".join(
                    f"{s},2000-11-01,2026-07-31\n" for s in world["frames"]))
            self.calls += 1
            parts = url.rstrip("/").split("/")
            source, n, first = parts[-4], int(parts[-2]), pd.Timestamp(parts[-1])
            frame = world["frames"][source]
            days = pd.to_datetime(frame["acq_date"])
            piece = frame[(days >= first) & (days < first + pd.Timedelta(days=n))]
            return FakeResponse(200, piece.to_csv(index=False))

    monkeypatch.delenv("PYRO_DEMO", raising=False)   # test_api.py forces demo mode for its own tests
    out = tmp_path / "firms"
    manifest = download((-124, 36, -119, 41), date(2018, 4, 1), date(2021, 12, 31), list(world["frames"]),
                        str(out), SECRET, chunk_days=10, pause=0, backoff=0, session=WorldSession(),
                        log=lambda *_: None)
    assert all(not v["failed_chunks"] for v in manifest["sources"].values())
    detections, loaded_manifest, info = load_dataset(str(out))
    assert info["mode"] == "firms" and loaded_manifest["bbox"] == [-124, 36, -119, 41]
    assert len(detections) == sum(len(f) for f in world["frames"].values())      # nothing lost or duplicated
    result = run_analysis(detections, loaded_manifest, AnalysisConfig(), info)
    assert result.summary["calibrations"]["SNPP"]["status"] == "calibrated"
    assert result.summary["coverage_basis"] == "download manifest"

    block = readme_block(result.summary)
    assert "Suomi-NPP VIIRS" in block and "docs/case_study/REPORT.md" in block
    readme = tmp_path / "README.md"
    readme.write_text(f"# x\n\n{README_START}\nold\n{README_END}\n\ntail\n", encoding="utf-8")
    assert update_readme(str(readme), block) is True
    text = readme.read_text(encoding="utf-8")
    assert "old" not in text and text.startswith("# x") and text.rstrip().endswith("tail") and block in text
    plain = tmp_path / "plain.md"
    plain.write_text("no markers", encoding="utf-8")
    assert update_readme(str(plain), block) is False and plain.read_text() == "no markers"



def test_limit_answered_with_http_400_waits_instead_of_failing(tmp_path):
    session = FakeSession(script={2: FakeResponse(400, "Exceeding allowed transaction limit."),
                                  3: FakeResponse(400, "Exceeding allowed transaction limit.")})
    logs = []
    manifest = download((-124, 36, -119, 41), date(2020, 8, 1), date(2020, 8, 15), ["VIIRS_SNPP_SP"],
                        str(tmp_path), SECRET, pause=0, backoff=0, limit_wait=0, session=session,
                        log=logs.append)
    entry = manifest["sources"]["VIIRS_SNPP_SP"]
    assert entry["failed_chunks"] == [] and entry["coverage"] == [["2020-08-01", "2020-08-15"]]
    assert any("transaction limit" in line for line in logs)


def test_other_http_400_shows_the_firms_message(tmp_path):
    session = FakeSession(script={1: FakeResponse(400, "Invalid area coordinates.")})
    manifest = download((-124, 36, -119, 41), date(2020, 8, 1), date(2020, 8, 5), ["VIIRS_SNPP_SP"],
                        str(tmp_path), SECRET, pause=0, backoff=0, limit_wait=0, session=session,
                        log=lambda *_: None)
    error = manifest["sources"]["VIIRS_SNPP_SP"]["failed_chunks"][0]["error"]
    assert "Invalid area coordinates" in error and SECRET not in error


def test_readme_lists_every_real_case_study_and_skips_synthetic(tmp_path):
    import json as _json
    from scripts.run_case_study import readme_block_all

    def summary(label, bbox, synthetic=False):
        cal = {"status": "calibrated", "reason": "", "selected_count_method": "detection_model",
               "method_labels": {"detection_model": "Detection model", "gridded_cells": "Grid"},
               "forward_in_time_test": {"count": {"detection_model": {"available": True, "total_bias_pct": -3.5}}},
               "cross_validation": {"count": {
                   "raw_hotspots": {"total_bias_pct": 781.2},
                   "gridded_cells": {"total_bias_pct": 222.0},
                   "detection_model": {"total_bias_pct": 1.6, "median_abs_pct_error": 14.1, "months": 81}}}}
        return {"synthetic": synthetic, "label": label, "area": {"bbox_west_south_east_north": bbox},
                "period": {"start": "2018-04-01", "end": "2024-12-31"},
                "platforms": [{"platform": "NOAA20", "label": "NOAA-20 VIIRS", "detections": 10}],
                "calibrations": {"NOAA20": cal}}

    for folder, s in (("case_study", summary("Northern California", [-124, 36, -119, 41])),
                      ("case_study_portugal", summary("Portugal", [-9.6, 36.9, -6.1, 42.2])),
                      ("synthetic_selftest", summary("Simulated", [0, 0, 1, 1], synthetic=True))):
        (tmp_path / "docs" / folder).mkdir(parents=True)
        (tmp_path / "docs" / folder / "report.json").write_text(_json.dumps(s), encoding="utf-8")
    block = readme_block_all(str(tmp_path))
    assert block.index("Northern California") < block.index("Portugal")
    assert "docs/case_study_portugal/REPORT.md" in block and "Simulated" not in block
    assert "Each region was fitted and tested on its own data." in block
