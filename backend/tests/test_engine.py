from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def recommend(body: dict):
    return client.post("/recommend", json=body)


def test_nothing_available():
    result = recommend({"challenge": "Flood"}).json()
    assert result["counts"] == {"needs_complementary_data": 33, "inputs_not_recorded": 1}
    assert "directly_applicable" not in result["counts"]


def test_rainfall_makes_kinematic_wave_direct():
    body = {"challenge": "Flood", "available_variables": ["RainfallIntensity"]}
    result = recommend(body).json()
    assert result["counts"]["directly_applicable"] == 1
    top = result["results"][0]
    assert top["id"] == "KinematicWave"
    assert top["score"] == 0.8


def test_several_variables():
    body = {
        "challenge": "Flood",
        "available_variables": ["RainfallIntensity", "HydraulicHead", "Discharge", "Precipitation"],
    }
    counts = recommend(body).json()["counts"]
    assert counts == {"directly_applicable": 6, "needs_complementary_data": 27, "inputs_not_recorded": 1}


def test_process_filter():
    result = recommend({"challenge": "Flood", "processes": ["Runoff"]}).json()
    assert len(result["results"]) == 12


def test_invalid_urr_is_rejected():
    body = {"challenge": "Flood", "available_variables": ["Banana"]}
    assert recommend(body).status_code == 422

def test_scale_filter_hides_methods():
    base = client.post("/recommend", json={"challenge": "Flood"}).json()
    narrowed = client.post(
        "/recommend", json={"challenge": "Flood", "scales": ["HillslopeScale"]}
    ).json()
    assert base["filtered_out"] == 0
    assert 0 < len(narrowed["results"]) < len(base["results"])
    assert narrowed["filtered_out"] == len(base["results"]) - len(narrowed["results"])
def test_check_method_needs_data():
    response = client.post("/methods/KinematicWave/check", json={"available_variables": []})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "needs_complementary_data"
    assert [i["id"] for i in result["inputs_missing"]] == ["RainfallIntensity"]


def test_check_method_ready():
    response = client.post(
        "/methods/KinematicWave/check", json={"available_variables": ["RainfallIntensity"]}
    )
    result = response.json()
    assert result["status"] == "directly_applicable"
    assert result["inputs_missing"] == []
    assert result["coverage"] == 1.0


def test_check_unknown_variable_is_422():
    response = client.post("/methods/KinematicWave/check", json={"available_variables": ["Nope"]})
    assert response.status_code == 422


def test_check_unknown_method_is_404():
    assert client.post("/methods/NoSuchMethod/check", json={}).status_code == 404
def test_reach_without_data():
    response = client.post("/reach", json={"available_variables": []})
    assert response.status_code == 200
    challenges = response.json()["challenges"]
    assert len(challenges) == 6
    assert all(c["counts"].get("directly_applicable", 0) == 0 for c in challenges)


def test_reach_with_data():
    data = ["RainfallIntensity", "HydraulicHead", "Discharge", "Precipitation"]
    challenges = client.post("/reach", json={"available_variables": data}).json()["challenges"]
    flood = next(c for c in challenges if c["id"] == "Flood")
    assert flood["counts"]["directly_applicable"] == 6
    assert len(flood["best"]) == 3


def test_reach_unknown_variable_is_422():
    assert client.post("/reach", json={"available_variables": ["Nope"]}).status_code == 422
def test_workflow_graph():
    response = client.post(
        "/workflow",
        json={"challenge": "Flood", "processes": ["Runoff"], "available_variables": ["Precipitation"]},
    )
    assert response.status_code == 200
    graph = response.json()
    ids = {n["id"] for n in graph["nodes"]}
    kinds = {n["kind"] for n in graph["nodes"]}
    assert {"challenge", "process", "method"} <= kinds
    assert "challenge:Flood" in ids
    assert len([n for n in graph["nodes"] if n["kind"] == "method"]) <= 3
    for edge in graph["edges"]:
        assert edge["source"] in ids and edge["target"] in ids


def test_workflow_can_focus_on_one_method():
    body = {"challenge": "Flood", "processes": ["Runoff"]}
    graph = client.post("/workflow", json=body).json()
    method_ids = [n["id"] for n in graph["nodes"] if n["kind"] == "method"]
    wanted = method_ids[0].split(":")[1]

    focused = client.post("/workflow", json={**body, "methods": [wanted]}).json()
    assert [n["id"] for n in focused["nodes"] if n["kind"] == "method"] == [method_ids[0]]


def test_workflow_unknown_challenge_is_422():
    assert client.post("/workflow", json={"challenge": "Nope"}).status_code == 422