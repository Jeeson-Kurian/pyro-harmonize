"""HTTP layer. Skipped automatically when FastAPI or its test client are not installed."""

import os

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("starlette.testclient")

os.environ["PYRO_DEMO"] = "1"          # the API tests always run on the labelled synthetic data

from starlette.testclient import TestClient   # noqa: E402

import app as app_module                       # noqa: E402


@pytest.fixture(scope="module")
def client():
    return TestClient(app_module.app)


def test_health_and_meta(client):
    assert client.get("/api/health").json()["status"] == "ok"
    meta = client.get("/api/meta").json()
    assert meta["synthetic"] is True and meta["mode"] == "synthetic"
    assert len(meta["bbox"]) == 4


def test_analysis_is_valid_json_without_nan(client):
    response = client.get("/api/analysis")
    assert response.status_code == 200
    assert "NaN" not in response.text and "Infinity" not in response.text
    body = response.json()
    assert body["synthetic"] is True
    assert body["notes"][0].startswith("SYNTHETIC DATA")
    assert len(body["calendar"]["harmonized_cells"][0]) == 366
    assert body["headline_validation"]["method"] in ("gridded_cells", "ratio_scaled", "detection_model",
                                                     "detection_model_seasonal")


def test_area_and_period_selection(client):
    q = "west=-123&south=37&east=-120&north=40&start=2015-01-01&end=2020-12-31"
    body = client.get("/api/analysis?" + q).json()
    assert body["period"]["start"] == "2015-01-01" and body["period"]["end"] == "2020-12-31"
    assert body["area"]["bbox_west_south_east_north"] == [-123.0, 37.0, -120.0, 40.0]


@pytest.mark.parametrize("query", ["west=5", "west=10&south=0&east=5&north=1", "start=2020-13-01",
                                   "start=2021-01-01&end=2020-01-01", "cell_km=500"])
def test_bad_requests_are_rejected_with_a_message(client, query):
    response = client.get("/api/analysis?" + query)
    assert response.status_code == 400 and response.json()["detail"]


def test_exports_carry_provenance(client):
    daily = client.get("/api/export/daily.csv")
    assert daily.status_code == 200 and daily.headers["content-type"].startswith("text/csv")
    header, first = daily.text.splitlines()[:2]
    assert header.startswith("data_mode,local_date")
    assert first.startswith("SYNTHETIC - not satellite data")
    det = client.get("/api/export/detections.csv?start=2020-08-01&end=2020-08-03").text.splitlines()
    for column in ("platform", "acq_datetime_utc", "version", "processing", "firms_source", "confidence_class"):
        assert column in det[0]
    assert client.get("/api/export/unknown.csv").status_code == 404


def test_clusters_and_sensitivity(client):
    body = client.get("/api/clusters?date_from=2020-08-01&date_to=2020-08-05&eps_km=2").json()
    assert body["total_clusters"] >= body["shown"] > 0
    assert "not a confirmed fire" in body["note"]
    assert client.get("/api/clusters?date_from=2020-08-01&date_to=2020-08-05&eps_km=99").status_code == 400
    rows = client.get("/api/sensitivity").json()["rows"]
    assert {r["eps_km"] for r in rows} == {0.5, 1.0, 2.0, 5.0}


def test_index_page_is_served(client):
    page = client.get("/")
    assert page.status_code == 200 and "PyroHarmonize" in page.text
