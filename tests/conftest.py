"""Shared fixtures. All test data are SYNTHETIC (engine/synthetic.py) or tiny hand-written FIRMS-layout tables."""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.data_loader import standardize_firms          # noqa: E402
from engine.pipeline import AnalysisConfig, run_analysis   # noqa: E402
from engine.synthetic import generate_synthetic_firms      # noqa: E402


def standardize_world(world):
    return pd.concat([standardize_firms(frame, source=source)
                      for source, frame in world["frames"].items()], ignore_index=True)


@pytest.fixture(scope="session")
def world():
    """2008-2023, Terra + Aqua + S-NPP + NOAA-20, no Aqua outage, no built-in trend."""
    return generate_synthetic_firms(start="2008-01-01", end="2023-12-31", seed=11, aqua_outage=None)


@pytest.fixture(scope="session")
def detections(world):
    return standardize_world(world)


@pytest.fixture(scope="session")
def analysis(world, detections):
    return run_analysis(detections, world["manifest"], AnalysisConfig())
