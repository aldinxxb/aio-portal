"""Run with:  pytest      (from the backend folder). Needs GraphDB running with v0.8.0 loaded.

Lesson 38: the options of the problem-definition steps (goal, driver, water entity, output).
"""
from fastapi.testclient import TestClient

from app import ontology, rules
from app.main import app
from app.urr import URR

client = TestClient(app)


def options(step: str, **draft):
    response = client.post(f"/options/{step}", json=draft)
    assert response.status_code == 200, response.text
    return {o["id"]: o for o in response.json()["options"]}


# ---- goal ---------------------------------------------------------------------

def test_goal_options_are_the_six_study_objectives():
    goals = options("objective", challenge="Flood")
    assert set(goals) == {
        "Forecasting", "Estimation", "ThresholdDetection",
        "Optimization", "Classification", "Simulation",
    }


def test_goal_count_is_what_the_rules_leave():
    goals = options("objective", challenge="Flood")
    all_methods = len(ontology.list_methods("Flood"))
    judged = rules.judge_methods(URR(challenge="Flood", objective="Forecasting"))
    assert goals["Forecasting"]["count"] == all_methods - judged["excluded"]
    assert goals["Forecasting"]["count"] < all_methods      # a hard rule removes methods
    assert goals["Simulation"]["count"] == all_methods      # no rule: nothing removed


# ---- driver -------------------------------------------------------------------

def test_driver_options_are_the_key_drivers_of_the_challenge():
    drivers = options("driver", challenge="Flood")
    assert {"Rainfall", "Urbanization"} <= set(drivers)
    assert "PollutionSources" not in drivers                # key driver of water quality only
    assert not any(d["suggested"] for d in drivers.values())  # flood has no default driver


def test_default_driver_is_suggested_and_explained():
    drivers = options("driver", challenge="ClimateChange")
    default = drivers["ClimateChangeFactor"]
    assert default["suggested"] is True and "skip" in default["hint"]
    assert [d for d in drivers if drivers[d]["suggested"]] == ["ClimateChangeFactor"]


def test_driver_count_follows_the_driver_rule():
    # climate change implies "the driver must be an input of the method"
    drivers = options("driver", challenge="ClimateChange")
    all_methods = len(ontology.list_methods("ClimateChange"))
    assert any(d["count"] < all_methods for d in drivers.values())


# ---- water entity -------------------------------------------------------------

def test_entity_without_output_is_greyed_out():
    entities = options("entity", challenge="Flood")
    assert len(entities) == 19
    assert entities["River"]["enabled"] is True and entities["River"]["count"] > 0
    aquifer = entities["Aquifer"]                           # no flood output concerns an aquifer
    assert aquifer["enabled"] is False and aquifer["count"] == 0 and aquifer["reason"]


def test_entity_count_shrinks_with_the_goal():
    free = options("entity", challenge="Flood")
    forecast = options("entity", challenge="Flood", objective="Forecasting")
    assert forecast["River"]["count"] < free["River"]["count"]


# ---- output -------------------------------------------------------------------

def test_output_options_primary_first_with_plain_question():
    response = client.post("/options/output", json={"challenge": "Flood"})
    listed = response.json()["options"]
    assert {o["id"] for o in listed if o["suggested"]} == {"Hydrograph", "FloodExtentMap"}
    assert listed[0]["suggested"] is True
    hydro = next(o for o in listed if o["id"] == "Hydrograph")
    assert hydro["hint"].startswith("How much water")
    assert all(o["enabled"] for o in listed)                # no entity chosen: nothing greyed


def test_output_must_concern_the_chosen_entity():
    outputs = options("output", challenge="Flood", entity="UrbanArea")
    assert outputs["FloodExtentMap"]["enabled"] is True
    hydro = outputs["Hydrograph"]                           # a hydrograph is about a river
    assert hydro["enabled"] is False and "water entity" in hydro["reason"]


def test_map_output_leaves_fewer_methods_than_a_series():
    outputs = options("output", challenge="Flood")
    assert 0 < outputs["FloodExtentMap"]["count"] < outputs["WaterLevelSeries"]["count"]


# ---- errors -------------------------------------------------------------------

def test_new_steps_need_a_challenge():
    for step in ("objective", "driver", "entity", "output"):
        assert client.post(f"/options/{step}", json={}).status_code == 422


def test_unknown_earlier_answer_is_422():
    bad = client.post("/options/output", json={"challenge": "Flood", "entity": "Banana"})
    assert bad.status_code == 422 and "Unknown entity: Banana" in bad.json()["detail"]


def test_old_steps_have_the_same_shape():
    flood = options("challenge")["Flood"]
    assert flood["hint"] is None and flood["suggested"] is False


# ---- Lesson 41: variables behind an output, method details ---------------------

def test_output_option_lists_its_variables():
    outputs = options("output", challenge="Flood")
    assert [v["id"] for v in outputs["Hydrograph"]["related"]] == ["Discharge"]
    assert {v["id"] for v in outputs["FloodHazardMap"]["related"]} == {"WaterLevel", "FlowVelocity"}
    assert outputs["Hydrograph"]["related"][0]["label"] == "discharge"


def test_results_carry_parameters_outputs_and_software():
    body = client.post("/recommend", json={"challenge": "Flood", "outputs": ["Hydrograph"]}).json()
    assert body["expected_outputs"][0]["id"] == "Hydrograph"
    assert [v["id"] for v in body["expected_outputs"][0]["variables"]] == ["Discharge"]
    scs = next(r for r in body["results"] if r["id"] == "SCS-CN")
    assert "ImperviousFraction" in [p["id"] for p in scs["physical_parameters"]]
    assert "HEC-HMS" in [s["id"] for s in scs["software"]]
    for result in body["results"]:
        for key in ("physical_parameters", "calibration_parameters", "outputs", "software"):
            assert isinstance(result[key], list)


def test_shared_software_is_always_kept():
    from collections import Counter

    from app import engine

    software = [{"id": x, "label": x} for x in ("A", "B", "C", "D", "E")]
    shared = Counter({"A": 1, "B": 1, "C": 1, "D": 2, "E": 3})
    picked = [s["id"] for s in engine.pick_software(software, shared, limit=3)]
    assert picked == ["E", "D", "A"]                     # most shared first, then cut at 3
    shared = Counter({"A": 2, "B": 2, "C": 2, "D": 2, "E": 1})
    assert [s["id"] for s in engine.pick_software(software, shared, limit=3)] == ["A", "B", "C", "D"]
