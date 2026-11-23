"""Run with:  pytest      (from the backend folder). Needs GraphDB running with v0.8.0 loaded."""
import pytest
from fastapi.testclient import TestClient

from app import ontology
from app.main import app
from app.urr import URR, validate

client = TestClient(app)


def ids(items):
    return {i["id"] for i in items}


def test_study_objectives():
    assert ids(ontology.list_vocabulary("objective")) == {
        "Forecasting", "Estimation", "ThresholdDetection",
        "Optimization", "Classification", "Simulation",
    }


def test_intents_scenarios_entities_counts():
    assert len(ontology.list_vocabulary("intent")) == 5
    assert len(ontology.list_vocabulary("scenario")) == 4
    assert len(ontology.list_vocabulary("entity")) == 19


def test_unknown_vocabulary_refused():
    with pytest.raises(ValueError):
        ontology.list_vocabulary("banana")


def test_flood_outputs_primary_first():
    outputs = ontology.list_outputs("Flood")
    assert ids(outputs) >= {"Hydrograph", "FloodExtentMap", "PeakFlow"}
    assert {o["id"] for o in outputs if o["primary"]} == {"Hydrograph", "FloodExtentMap"}
    assert outputs[0]["primary"] is True
    hydro = next(o for o in outputs if o["id"] == "Hydrograph")
    assert "River" in hydro["entities"] and hydro["question"].startswith("How much water")


def test_flood_drivers_and_climate_change_default():
    assert ids(ontology.list_drivers("Flood")) >= {"Rainfall", "Urbanization"}
    cc = ontology.list_drivers("ClimateChange")
    assert [d["id"] for d in cc if d["default"]] == ["ClimateChangeFactor"]


def test_urr_accepts_new_fields():
    result = validate(URR(challenge="Flood", objective="Forecasting", intent="Prediction",
                          scenario="CurrentScenario", entity="River",
                          drivers=["Rainfall"], outputs=["Hydrograph"]))
    assert result["valid"], result["problems"]
    assert result["urr"]["objective"] == "Forecasting"


def test_urr_refuses_unknown_goal():
    result = validate(URR(challenge="Flood", objective="Banana"))
    assert not result["valid"] and "Unknown objective: Banana" in result["problems"]


def test_vocabulary_routes():
    assert client.get("/vocabulary/objective").status_code == 200
    assert client.get("/vocabulary/banana").status_code == 404
    assert client.get("/challenges/Flood/outputs").status_code == 200
    assert client.get("/challenges/Banana/outputs").status_code == 404