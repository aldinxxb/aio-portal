"""Run with:  pytest      (from the backend folder). Needs GraphDB running with v0.7.0 loaded.

The first group needs no database: it tests the rule logic with hand-made facts.
"""
from fastapi.testclient import TestClient

from app import ontology, requirements, rules
from app.main import app
from app.urr import URR

client = TestClient(app)


def make_requirement(**changes):
    base = {
        "id": "Req_Test", "kind": "method", "label": "test", "rationale": "because",
        "strength": "hard", "weight": 0.0, "rule_id": None, "on_property": None,
        "allowed_values": [], "allowed_literal": None, "applies_to": [], "because": [],
    }
    return {**base, **changes}


# ---- rule logic, no database ------------------------------------------------

def test_hard_value_rule_excludes_a_method_that_fails():
    req = make_requirement(on_property="hasTemporalMode", allowed_values=["Continuous"])
    verdict = rules.judge({"hasTemporalMode": ["EventBased"]}, [req], {})
    assert verdict["excluded"] is True
    assert verdict["reasons"][0]["status"] == "fail"


def test_hard_value_rule_keeps_a_method_that_passes():
    req = make_requirement(on_property="hasTemporalMode", allowed_values=["Continuous"])
    verdict = rules.judge({"hasTemporalMode": ["Continuous", "EventBased"]}, [req], {})
    assert verdict["excluded"] is False


def test_missing_information_never_excludes():
    req = make_requirement(on_property="hasTemporalMode", allowed_values=["Continuous"])
    verdict = rules.judge({}, [req], {})
    assert verdict["excluded"] is False
    assert verdict["reasons"][0]["status"] == "unknown"


def test_soft_rule_adds_the_weight_or_loses_half_of_it():
    req = make_requirement(strength="soft", weight=0.10,
                           on_property="hasSpatialRepresentation", allowed_values=["Lumped"])
    assert rules.judge({"hasSpatialRepresentation": ["Lumped"]}, [req], {})["adjustment"] == 0.10
    assert rules.judge({"hasSpatialRepresentation": ["FullyDistributed"]}, [req], {})["adjustment"] == -0.05


def test_pattern_rule_and_unknown_rule_id():
    few = make_requirement(strength="soft", weight=0.05, rule_id="few-calibration-parameters")
    assert rules.judge({"hasCalibrationParameter": ["a", "b", "c"]}, [few], {})["adjustment"] == -0.025
    odd = make_requirement(rule_id="rule-that-does-not-exist")
    verdict = rules.judge({}, [odd], {})
    assert verdict["excluded"] is False and verdict["reasons"][0]["status"] == "unknown"


# ---- with GraphDB -------------------------------------------------------------

def test_forecasting_requirements_hard_first():
    reqs = requirements.collect(URR(challenge="Flood", objective="Forecasting"))
    ids = {r["id"] for r in reqs}
    assert {"Req_ContinuousMode", "Req_ForecastData", "Req_CalibrationDataAvailable"} <= ids
    assert reqs[0]["strength"] == "hard"
    cont = next(r for r in reqs if r["id"] == "Req_ContinuousMode")
    assert cont["kind"] == "method" and cont["on_property"] == "hasTemporalMode"
    assert cont["allowed_values"] == ["Continuous"] and cont["because"] == ["Forecasting"]


def test_one_requirement_keeps_every_cause():
    reqs = requirements.collect(URR(challenge="Flood", intent="ImpactAnalysis", scenario="WhatIfScenario"))
    driver_rule = next(r for r in reqs if r["id"] == "Req_DriverIsInput")
    assert set(driver_rule["because"]) == {"ImpactAnalysis", "WhatIfScenario"}


def test_climate_change_uses_its_default_driver():
    urr = URR(challenge="ClimateChange")
    assert requirements.effective_drivers(urr) == ["ClimateChangeFactor"]
    ids = {r["id"] for r in requirements.collect(urr)}
    assert {"Req_DriverIsInput", "Req_PreferProjectionData"} <= ids


def test_forecasting_excludes_exactly_the_non_continuous_methods():
    out = rules.judge_methods(URR(challenge="Flood", objective="Forecasting"))
    facts = ontology.method_facts()
    assert out["excluded"] > 0 and len(out["methods"]) > 10
    for method in out["methods"]:
        modes = facts.get(method["id"], {}).get("hasTemporalMode", [])
        assert method["excluded"] == ("Continuous" not in modes)


def test_requirement_routes():
    body = {"challenge": "Flood", "objective": "Forecasting"}
    reqs = client.post("/requirements", json=body)
    assert reqs.status_code == 200 and reqs.json()[0]["strength"] == "hard"
    check = client.post("/rules/check", json=body)
    assert check.status_code == 200 and check.json()["excluded"] > 0
    bad = client.post("/rules/check", json={"challenge": "Flood", "objective": "Banana"})
    assert bad.status_code == 422