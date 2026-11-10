"""Run with:  pytest      (from the backend folder). Needs GraphDB running with v0.7.0 loaded.

The first group needs no database: it tests how verdicts change a ranked list.
"""
from fastapi.testclient import TestClient

from app import engine, ontology
from app.main import app

client = TestClient(app)


def make_result(method_id, score):
    return {"id": method_id, "label": method_id, "status": engine.DIRECT, "score": score}


def make_verdict(excluded=False, adjustment=0.0, reasons=None):
    return {"excluded": excluded, "adjustment": adjustment, "reasons": reasons or []}


# ---- combining results and verdicts, no database ------------------------------

def test_excluded_method_leaves_the_list_and_is_explained():
    why = {"requirement": "Req_ContinuousMode", "strength": "hard", "status": "fail", "detail": "x"}
    other = {"requirement": "Req_FastRuns", "strength": "soft", "status": "fail", "detail": "y"}
    kept, excluded = engine.apply_verdicts(
        [make_result("A", 0.9), make_result("B", 0.8)],
        {"A": make_verdict(excluded=True, reasons=[why, other]), "B": make_verdict()},
    )
    assert [r["id"] for r in kept] == ["B"]
    assert excluded == [{"id": "A", "label": "A", "reasons": [why]}]  # only the hard failure


def test_soft_adjustment_changes_the_score_and_keeps_the_base_score():
    kept, _ = engine.apply_verdicts([make_result("A", 0.80)], {"A": make_verdict(adjustment=0.15)})
    assert kept[0]["score"] == 0.95
    assert kept[0]["base_score"] == 0.80 and kept[0]["rule_adjustment"] == 0.15


def test_score_stays_between_0_and_1():
    kept, _ = engine.apply_verdicts(
        [make_result("A", 0.98), make_result("B", 0.02)],
        {"A": make_verdict(adjustment=0.3), "B": make_verdict(adjustment=-0.3)},
    )
    assert kept[0]["score"] == 1.0 and kept[1]["score"] == 0.0


def test_method_without_score_stays_without_score():
    kept, _ = engine.apply_verdicts([make_result("A", None)], {"A": make_verdict(adjustment=0.1)})
    assert kept[0]["score"] is None


def test_has_problem():
    assert engine.has_problem({"objective": "Forecasting"}) is True
    assert engine.has_problem({"drivers": ["Rainfall"]}) is True
    assert engine.has_problem({"challenge": "Flood", "objective": None, "drivers": []}) is False


# ---- with GraphDB -------------------------------------------------------------

def recommend(**fields):
    response = client.post("/recommend", json={"challenge": "Flood", **fields})
    assert response.status_code == 200, response.text
    return response.json()


def test_without_a_problem_nothing_changes():
    body = recommend(available_variables=["Precipitation"])
    assert body["rules_applied"] is False
    assert body["excluded_by_rules"] == 0 and body["requirements"] == []


def test_forecasting_removes_exactly_the_non_continuous_methods():
    plain = recommend()
    forecast = recommend(objective="Forecasting")
    assert forecast["rules_applied"] is True
    assert forecast["excluded_by_rules"] > 0
    assert len(forecast["results"]) + forecast["excluded_by_rules"] == len(plain["results"])
    facts = ontology.method_facts()
    for result in forecast["results"]:
        assert "Continuous" in facts[result["id"]]["hasTemporalMode"]
        assert result["reasons"]            # every kept method explains itself


def test_excluded_methods_are_explained():
    body = recommend(objective="Forecasting")
    assert body["excluded_methods"]
    for method in body["excluded_methods"]:
        assert method["reasons"] and all(
            r["strength"] == "hard" and r["status"] == "fail" for r in method["reasons"]
        )


def test_scores_follow_the_soft_rules():
    body = recommend(objective="Forecasting", available_variables=["Discharge", "Precipitation"])
    scored = [r for r in body["results"] if r["score"] is not None]
    assert scored
    for r in scored:
        expected = min(1.0, max(0.0, r["base_score"] + r["rule_adjustment"]))
        assert abs(r["score"] - expected) < 0.002
        