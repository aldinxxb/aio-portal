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
    assert sum(1 for m in methods if not m["inputs"]) == 0


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