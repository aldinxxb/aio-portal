import pytest
from fastapi.testclient import TestClient

from app import queries
from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_challenges_include_flood():
    data = client.get("/challenges").json()
    ids = {c["id"] for c in data}
    assert len(data) == 6
    assert "Flood" in ids


def test_flood_processes():
    ids = {p["id"] for p in client.get("/challenges/Flood/processes").json()}
    assert ids == {
        "ChannelFlow",
        "GroundWaterFlow",
        "Infiltration",
        "Runoff",
        "SedimentTransport",
        "Snowmelt",
    }


def test_flood_methods():
    methods = client.get("/challenges/Flood/methods").json()
    assert len(methods) == 34
    kinematic = next(m for m in methods if m["id"] == "KinematicWave")
    assert "RainfallIntensity" in {i["id"] for i in kinematic["inputs"]}
    assert [m["id"] for m in methods if not m["inputs"]] == ["DarcyEquation3D"]  # heads are an initial condition


def test_unknown_challenge_is_404():
    assert client.get("/challenges/Nope/methods").status_code == 404


def test_injection_is_refused():
    with pytest.raises(ValueError):
        queries.build("processes_of_challenge", challenge="Flood> } #")
def test_method_profile():
    response = client.get("/methods/KinematicWave")
    assert response.status_code == 200
    profile = response.json()
    assert profile["label"] == "Kinematic Wave"
    assert "RainfallIntensity" in [i["id"] for i in profile["mandatory_inputs"]]
    assert "HEC-HMS" in [s["id"] for s in profile["software"]]
    assert "Flood" in [c["id"] for c in profile["challenges"]]


def test_unknown_method_is_404():
    assert client.get("/methods/NoSuchMethod").status_code == 404

def test_datasets_for_precipitation():
    response = client.post("/datasets", json={"variables": ["Precipitation"]})
    assert response.status_code == 200
    datasets = response.json()["datasets"]
    assert len(datasets) > 0
    for dataset in datasets:
        assert "Precipitation" in [v["id"] for v in dataset["provides"]]


def test_datasets_without_variables_is_empty():
    response = client.post("/datasets", json={"variables": []})
    assert response.json()["datasets"] == []


def test_datasets_unknown_variable_is_422():
    assert client.post("/datasets", json={"variables": ["Nope"]}).status_code == 422

# ---- Lesson 42: dataset search by variable name --------------------------------

def test_search_returns_every_dataset_with_the_variable():
    found = client.get("/datasets/search", params={"q": "precip"}).json()
    assert "Precipitation" in [v["id"] for v in found["variables"]]
    from app import ontology

    expected = [
        d["id"] for d in ontology.list_datasets()
        if any("precip" in (v["label"] or v["id"]).lower() for v in d["variables"])
    ]
    assert sorted(d["id"] for d in found["datasets"]) == sorted(expected)   # all of them, no limit
    for dataset in found["datasets"]:
        assert all("precip" in (v["label"] or v["id"]).lower() for v in dataset["provides"])


def test_search_gives_temporal_and_spatial_facts():
    found = client.get("/datasets/search", params={"q": "precipitation"}).json()
    era5 = next(d for d in found["datasets"] if d["id"] == "ERA5")
    assert era5["start"] == "1940-01-01" and era5["ongoing"] is True
    assert era5["temporal_nature"] and "Global" in [a["id"] for a in era5["coverage"]]
    rain = next(v for v in era5["provides"] if v["id"] == "Precipitation")
    assert "1 hour" in rain["time_steps"] and "0.25°" in rain["grids"]


def test_search_ignores_case_and_empty_text():
    assert client.get("/datasets/search", params={"q": "PRECIP"}).json()["datasets"]
    assert client.get("/datasets/search", params={"q": "  "}).json()["datasets"] == []
    assert client.get("/datasets/search", params={"q": "zzzz"}).json()["datasets"] == []


def test_dataset_variables_for_suggestions():
    variables = client.get("/datasets/variables").json()
    rain = next(v for v in variables if v["id"] == "Precipitation")
    assert rain["count"] > 1 and rain["label"]


def test_readable_resolutions():
    from app import ontology

    assert ontology.readable_duration("PT1H") == "1 hour"
    assert ontology.readable_duration("P10D") == "10 days"
    assert ontology.readable_duration("PT30M") == "30 minutes"
    assert ontology.readable_duration("P1M") == "1 month"
    assert ontology.readable_grid("8000.0", None) == "8 km"
    assert ontology.readable_grid("250.0", None) == "250 m"
    assert ontology.readable_grid(None, "0.25") == "0.25°"


def test_watersheds_of_a_study_area_come_from_bd_topage():
    """The second map: the BD Topage watersheds whose centre lies inside the chosen area."""
    from app import geo
    area = geo.layer("subbasins")["features"][0]
    response = client.get(f"/geo/watersheds/subbasins/{area['properties']['id']}")
    assert response.status_code == 200, response.text
    found = response.json()
    assert found["features"] and found["area"]["properties"]["id"] == area["properties"]["id"]
    x0, y0, x1, y1 = area["properties"]["bbox"]
    for feature in found["features"]:
        cx, cy = feature["properties"]["centre"]
        assert x0 <= cx <= x1 and y0 <= cy <= y1
    assert client.get("/geo/watersheds/subbasins/nowhere").status_code == 404
