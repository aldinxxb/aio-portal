from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def options(step: str, body: dict):
    return client.post(f"/options/{step}", json=body)


def test_challenge_options_have_counts():
    result = options("challenge", {}).json()["options"]
    counts = {o["id"]: o["count"] for o in result}
    assert len(result) == 6
    assert counts["Flood"] == 34
    assert counts["WaterQuality"] == 35


def test_process_options_for_flood():
    result = options("process", {"challenge": "Flood"}).json()["options"]
    counts = {o["id"]: o["count"] for o in result}
    assert counts == {
        "ChannelFlow": 9,
        "GroundWaterFlow": 6,
        "Infiltration": 9,
        "Runoff": 12,
        "SedimentTransport": 4,
        "Snowmelt": 1,
    }
    assert all(o["enabled"] for o in result)


def test_process_without_methods_is_greyed_out():
    import pytest

    challenges = [o["id"] for o in options("challenge", {}).json()["options"]]
    empty = []
    for challenge in challenges:
        for o in options("process", {"challenge": challenge}).json()["options"]:
            if o["count"] == 0:
                empty.append(o)
    if not empty:
        pytest.skip("every process has at least one method in this ontology version")
    # the rule: no method -> disabled, and the user is told why
    assert all(o["enabled"] is False and o["reason"] for o in empty)

def test_step_needs_previous_answer():
    assert options("process", {}).status_code == 422


def test_unknown_step_is_404():
    assert options("nonsense", {}).status_code == 404


def test_unknown_challenge_is_422():
    assert options("process", {"challenge": "Nope"}).status_code == 422


def test_variable_options_for_flood():
    response = client.post("/options/variable", json={"challenge": "Flood"})
    assert response.status_code == 200
    options = response.json()["options"]
    ids = [o["id"] for o in options]
    assert "Precipitation" in ids
    assert "Discharge" in ids
    assert all(o["count"] > 0 for o in options)


def test_variable_options_need_a_challenge():
    response = client.post("/options/variable", json={})
    assert response.status_code == 422

def test_scale_options_for_flood():
    options = client.post("/options/scale", json={"challenge": "Flood"}).json()["options"]
    ids = [o["id"] for o in options]
    assert "CatchmentScale" in ids
    assert all(o["count"] > 0 for o in options)


def test_timestep_options_for_flood():
    options = client.post("/options/timestep", json={"challenge": "Flood"}).json()["options"]
    ids = [o["id"] for o in options]
    assert "Daily" in ids
def test_software_options():
    options = client.post("/options/software", json={}).json()["options"]
    ids = [o["id"] for o in options]
    assert "SWAT" in ids
    assert all(o["count"] > 0 for o in options)


def test_methods_of_software():
    response = client.post("/options/method", json={"software": "SWAT"})
    assert response.status_code == 200
    assert len(response.json()["options"]) > 0


def test_method_step_needs_software():
    assert client.post("/options/method", json={}).status_code == 422   
def test_data_options():
    options = client.post("/options/data", json={}).json()["options"]
    ids = [o["id"] for o in options]
    assert "Precipitation" in ids
    assert all(o["count"] > 0 for o in options)