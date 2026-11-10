from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_variables_list():
    data = client.get("/variables").json()
    assert len(data) == 103
    assert "RainfallIntensity" in {v["id"] for v in data}


def test_valid_urr_derives_processes():
    body = {"challenge": "Flood", "available_variables": ["RainfallIntensity"]}
    result = client.post("/urr/validate", json=body).json()
    assert result["valid"] is True
    assert result["urr"]["processes"]["source"] == "derived"
    assert len(result["urr"]["processes"]["values"]) == 6


def test_invalid_urr_lists_problems():
    body = {"challenge": "Flood", "processes": ["Recharge"], "available_variables": ["Banana"]}
    result = client.post("/urr/validate", json=body).json()
    assert result["valid"] is False
    assert len(result["problems"]) == 2


def test_missing_challenge_is_rejected():
    assert client.post("/urr/validate", json={}).status_code == 422