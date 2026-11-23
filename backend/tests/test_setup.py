"""Run with:  pytest      (from the backend folder). Needs GraphDB running with v0.8.0 loaded.

Modeling Approach entry: diagnose a set-up and improve it. These are the acceptance
tests of the specification (section 8): structure only, no hard-coded score.
"""
import re

import pytest
from fastapi.testclient import TestClient

from app import chains, knowledge, queries, timesteps
from app.main import app
from app.sparql_client import run_select

client = TestClient(app)

FLOOD = {"challenge": "Flood", "objective": "Simulation"}


@pytest.fixture(scope="module")
def k():
    return knowledge.load()


def improve(methods, context=FLOOD, data=(), **setup):
    body = {"setup": {"methods": methods, **setup}, "context": context, "data": list(data)}
    response = client.post("/setup/improve", json=body)
    assert response.status_code == 200, response.text
    return body, response.json()


def codes(diagnosis, severity=None):
    return {i["code"] for i in diagnosis["issues"] if severity is None or i["severity"] == severity}


def merge(body, patch):
    """What the frontend does with the patch of an accepted action."""
    body = {"setup": dict(body["setup"]), "context": body["context"], "data": list(body["data"])}
    setup = body["setup"]
    setup.setdefault("roles", {})
    for key, value in patch.items():
        if key == "data+":
            names = {d["variable"] for d in value}
            body["data"] = [d for d in body["data"] if d["variable"] not in names] + value
        elif key == "setup.methods+":
            setup["methods"] = setup["methods"] + [m for m in value if m not in setup["methods"]]
        elif key == "setup.methods-":
            setup["methods"] = [m for m in setup["methods"] if m not in value]
        elif key == "setup.roles+":
            setup["roles"] = {**setup["roles"], **value}
        elif key == "setup":
            body["setup"] = {**setup, **value}
    return body


# ---- 1. vocabulary -----------------------------------------------------------------

def test_every_term_of_the_specification_exists():
    text = queries.load("vocabulary_check")
    # the core and its extensions (0.9.0): every term is looked for in its own module
    wanted = set(re.findall(r"\b(?:aio|aioreq|aiowf|aiosw|dcat|dct):[A-Za-z]+", text.split("VALUES")[1].split("}")[0]))
    prefixes = {"aio": "https://w3id.org/aio#", "dcat": "http://www.w3.org/ns/dcat#",
                "dct": "http://purl.org/dc/terms/", "aioreq": "https://w3id.org/aio/requirements#",
                "aiowf": "https://w3id.org/aio/workflow#", "aiosw": "https://w3id.org/aio/software#"}
    found = {row["term"] for row in run_select(text)}
    missing = sorted(t for t in wanted if prefixes[t.split(":")[0]] + t.split(":")[1] not in found)
    assert len(wanted) > 90 and missing == []


def test_every_method_has_a_role_and_a_time_step(k):
    methods = {r["s"].split("#")[-1] for r in run_select(
        "PREFIX aio: <https://w3id.org/aio#> SELECT ?s WHERE { ?s a aio:ModelingMethod }")}
    assert methods == set(k.facts)
    assert all(chains.get(k, m, "fillsRole") and chains.get(k, m, "supportsTimeStep") for m in methods)


# ---- 2. Clark alone -----------------------------------------------------------------

def test_clark_alone_needs_a_loss_method_and_the_patch_fixes_it(k):
    body, found = improve(["Clark-UH"])
    rain = next(d for d in found["diagnosis"]["data"] if d["id"] == "EffectiveRainfall")
    assert rain["status"] == "needs_component"
    feeds = [a for a in found["actions"] if a["kind"] == "feed_input"]
    assert feeds
    for action in feeds:
        assert "Role_ExcessRainfall" in chains.get(k, action["proposal"]["method"]["id"], "fillsRole")
    assert "SCS-CN" in {a["proposal"]["method"]["id"] for a in feeds}     # used with Clark in standard chains
    after = client.post("/setup/diagnose", json=merge(body, feeds[0]["patch"])).json()
    assert "MISSING_INPUT_COMPONENT" not in codes(after)


# ---- 3. extend the output -------------------------------------------------------------

def test_event_chain_needs_hydraulics_for_a_flood_extent_map(k):
    _, found = improve(["SCS-CN", "Clark-UH", "Muskingum-Cunge"], {**FLOOD, "output": "FloodExtentMap"})
    assert "OUTPUT_NEEDS_COMBINATION" in codes(found["diagnosis"], "blocking")
    extensions = [a for a in found["actions"] if a["kind"] == "extend_output"]
    assert extensions
    for action in extensions:
        method = action["proposal"]["methods"][-1]["id"]
        assert "Role_Hydraulics" in chains.get(k, method, "fillsRole")
        assert "WaterLevel" in chains.get(k, method, "producesOutput")
        assert "FullyDistributed" in chains.get(k, method, "hasSpatialRepresentation") or \
            set(chains.get(k, method, "hasDimensionality")) & {"Dim2D", "Dim3D"}
        assert timesteps.step_ok(k.hours, chains.get(k, "Muskingum-Cunge", "supportsTimeStep"),
                                 chains.get(k, method, "supportsTimeStep"))


def test_daily_model_cannot_drive_a_2d_flood_model(k):
    _, found = improve(["GR4Jmodel"], {**FLOOD, "output": "FloodExtentMap"})
    for action in found["actions"]:
        if action["kind"] == "extend_output":
            for method in action["proposal"]["methods"]:
                assert timesteps.step_ok(k.hours, chains.get(k, "GR4Jmodel", "supportsTimeStep"),
                                         chains.get(k, method["id"], "supportsTimeStep"))
    covered = [a for a in found["actions"]
               if "OUTPUT_NEEDS_COMBINATION:FloodExtentMap" in a["resolves"]]
    assert covered and (any(a["kind"] == "extend_output" for a in covered)
                        or any(a["kind"].startswith("replace_") for a in covered))


# ---- 4. objective rule ------------------------------------------------------------------

def test_event_only_method_cannot_forecast_and_a_continuous_one_is_proposed(k):
    assert chains.get(k, "SCS-UH", "hasTemporalMode") == ["EventBased"]
    _, found = improve(["SCS-UH"], {"challenge": "Flood", "objective": "Forecasting"})
    failed = [i for i in found["diagnosis"]["issues"] if i["code"] == "RULE_FAILED"]
    assert any(i["subject"] == "Req_ContinuousMode" and i["severity"] == "blocking" for i in failed)
    replacements = [a for a in found["actions"] if a["kind"] == "replace_method"]
    assert replacements
    for action in replacements:
        new = action["proposal"]["by"]["id"]
        assert "Role_RunoffTransform" in chains.get(k, new, "fillsRole")
        assert "Continuous" in chains.get(k, new, "hasTemporalMode")


# ---- 5-6. time step of the data ------------------------------------------------------------

def test_daily_rain_for_threshold_detection_could_be_finer():
    rain = [{"variable": "Precipitation", "step": "Daily"}]
    _, found = improve(["SCS-CN"], {"challenge": "Flood", "objective": "ThresholdDetection"}, rain)
    issue = next(i for i in found["diagnosis"]["issues"] if i["code"] == "STEP_COULD_BE_FINER")
    assert issue["severity"] == "warning"
    finer = [a for a in found["actions"] if a["kind"] == "finer_time_step"]
    assert finer and finer[0]["patch"]["data+"][0]["step"] in ("Hourly", "SubHourly")


def test_monthly_rain_is_too_coarse_for_an_hourly_method(k):
    assert "MonthlyOrLonger" not in chains.get(k, "Green-Ampt", "supportsTimeStep")
    _, found = improve(["Green-Ampt"], FLOOD, [{"variable": "Precipitation", "step": "MonthlyOrLonger"}])
    assert "STEP_TOO_COARSE" in codes(found["diagnosis"], "blocking")


# ---- 7-8. calibration data and initial state ------------------------------------------------

def test_observed_discharge_is_proposed_to_calibrate(k):
    assert "Discharge" in chains.get(k, "GR4Jmodel", "isCalibratedAgainst")
    _, found = improve(["GR4Jmodel"], {"challenge": "Drought", "objective": "Simulation"})
    proposed = [a for a in found["actions"] if a["kind"] == "add_calibration_data"]
    assert proposed and proposed[0]["proposal"]["variable"]["id"] == "Discharge"
    dataset = proposed[0]["proposal"]["dataset"]["id"]
    assert any(s["dataset"] == dataset and s["provenance"] in ("Observed", "RemoteSensingRetrieval")
               for s in k.data["Discharge"])


def test_initial_heads_are_an_initial_state_not_a_blocking_issue():
    _, found = improve(["FiniteDifferenceGroundwaterFlow"],
                       {"challenge": "WaterAvailabilty", "objective": "Simulation"})
    initial = [i for i in found["diagnosis"]["issues"] if i["code"] == "INITIAL_STATE"]
    assert initial and all(i["severity"] == "info" for i in initial)
    row = next(d for d in found["diagnosis"]["data"] if d["kind"] == "initial")
    assert row["status"] == "initial_state"


# ---- 9-10. ensemble and duplicate role -------------------------------------------------------

def test_impact_analysis_proposes_an_ensemble_of_two_alternatives(k):
    _, found = improve(["SCS-CN", "Clark-UH"], {**FLOOD, "intent": "ImpactAnalysis"})
    ensemble = next(a for a in found["actions"] if a["kind"] == "ensemble")
    assert len(ensemble["proposal"]["methods"]) == 2
    for method in ensemble["proposal"]["methods"]:
        assert method["id"] in chains.get(k, ensemble["subject"], "isAlternativeTo")


def test_two_methods_for_the_same_job_is_blocking():
    _, found = improve(["Clark-UH", "SCS-UH"])
    assert "DUPLICATE_ROLE" in codes(found["diagnosis"], "blocking")


def test_linear_reservoir_takes_the_job_that_is_free():
    # with Clark as the transform, Linear Reservoir is the baseflow method: no duplicate
    _, found = improve(["SCS-CN", "Clark-UH", "LinearReservoir", "Muskingum-Cunge"])
    assert "DUPLICATE_ROLE" not in codes(found["diagnosis"])
    reservoir = next(m for m in found["diagnosis"]["setup"]["methods"] if m["id"] == "LinearReservoir")
    assert [r["id"] for r in reservoir["roles"]] == ["Role_Baseflow"]
    assert [r["id"] for r in reservoir["can_also"]] == ["Role_RunoffTransform"]
    # stated explicitly as a transform next to Clark: now it is a duplicate
    _, found = improve(["Clark-UH", "LinearReservoir"], roles={"LinearReservoir": ["Role_RunoffTransform"]})
    assert "DUPLICATE_ROLE" in codes(found["diagnosis"], "blocking")


# ---- 11-13. actions -----------------------------------------------------------------------------

def test_generated_combinations_are_labelled_and_reference_chains_rank_first():
    _, found = improve(["Clark-UH"])
    combined = [a for a in found["actions"] if a["path"] == "combine" and a["kind"] != "adopt_reference_chain"]
    assert combined and all(a["standard_practice"] is False for a in combined)
    assert all("not a standard practice" in a["message"] for a in combined)
    adopted = [a for a in found["actions"] if a["kind"] == "adopt_reference_chain"]
    assert adopted and all(a["standard_practice"] is True for a in adopted)
    order = {"blocking": 0, "high": 1, "medium": 2, "low": 3}
    gains = [order[a["gain"]] for a in found["actions"]]
    assert gains == sorted(gains)                              # most useful first


def test_every_action_has_a_message_a_patch_and_does_not_lower_the_fit():
    for methods, context in ((["Clark-UH"], FLOOD),
                             (["GR4Jmodel"], {**FLOOD, "output": "FloodExtentMap"}),
                             (["SCS-CN"], {"challenge": "Flood", "objective": "ThresholdDetection"})):
        _, found = improve(methods, context)
        assert found["actions"]
        for action in found["actions"]:
            assert action["message"] and isinstance(action["patch"], dict)
            if action["kind"] != "add_component":   # an optional component may cost a little fit (more data to find)
                assert action["effect"]["fit_after"] >= action["effect"]["fit_before"]
            assert action["group"] in ("fix_first", "recommended", "optional")


def test_accepting_the_blocking_actions_one_by_one_removes_the_blocking_issues():
    body, found = improve(["Clark-UH"])
    for _ in range(6):                                         # the backend keeps nothing: we resend
        if found["diagnosis"]["fit"]["blocking"] == 0:
            break
        fixes = [a for a in found["actions"] if a["group"] == "fix_first" and a["patch"]]
        if not fixes:
            break
        body = merge(body, fixes[0]["patch"])
        found = client.post("/setup/improve", json=body).json()
    left = found["diagnosis"]["fit"]["blocking"]
    assert left == 0 or any(a["kind"].startswith("replace_") for a in found["actions"])


# ---- wizard options and errors -----------------------------------------------------------------

def options(step, **request):
    response = client.post("/setup/options", json={"step": step, "request": request})
    assert response.status_code == 200, response.text
    return response.json()


def test_methods_are_grouped_by_role_and_linear_reservoir_appears_twice():
    groups = options("methods", setup={"software": "HEC-HMS"})["groups"]
    under = [g["role"]["id"] for g in groups if any(o["id"] == "LinearReservoir" for o in g["options"])]
    assert sorted(under) == ["Role_Baseflow", "Role_RunoffTransform"]
    transform = next(g for g in groups if g["role"]["id"] == "Role_RunoffTransform")
    as_transform = next(o for o in transform["options"] if o["id"] == "LinearReservoir")
    assert "Discharge" in [v["id"] for v in as_transform["delivers"]]


def test_challenge_and_output_options_say_what_the_setup_can_reach():
    challenges = {o["id"]: o for o in options("challenge", setup={"methods": ["Clark-UH"]})["options"]}
    assert challenges["Flood"]["status"] == "ok"
    outputs = {o["id"]: o for o in options("output", setup={"methods": ["Clark-UH"]},
                                           context={"challenge": "Flood"})["options"]}
    assert outputs["Hydrograph"]["status"] == "ok"
    assert outputs["FloodExtentMap"]["status"] == "needs_combination"
    objectives = {o["id"]: o for o in options("objective", setup={"methods": ["SCS-UH"]})["options"]}
    assert objectives["Forecasting"]["status"] == "needs_change" and objectives["Forecasting"]["reason"]


def test_data_checklist_lists_the_inputs_with_their_nature():
    rows = options("data", setup={"methods": ["Saint-VenantEquations1D"]}, context=FLOOD)["options"]
    nature = {r["id"]: r["nature"] for r in rows}
    assert nature["Discharge"] == "boundary" and nature["ChannelGeometry"] == "static"
    rows = options("data", setup={"methods": ["SCS-CN"]}, context=FLOOD)["options"]
    assert {r["id"]: r["nature"] for r in rows}["Precipitation"] == "forcing"


def test_unknown_names_are_422():
    bad = client.post("/setup/diagnose", json={"setup": {"methods": ["Nope"]}, "context": FLOOD})
    assert bad.status_code == 422
    bad = client.post("/setup/diagnose", json={"setup": {"methods": []}, "context": FLOOD})
    assert bad.status_code == 422
    bad = client.post("/setup/diagnose", json={"setup": {"methods": ["Clark-UH"]},
                                              "context": {"challenge": "Flood"}})
    assert bad.status_code == 422                               # the objective is required


# ---- results of the Challenge entry: two views, roles, kinds of input -----------------------------

def test_processes_are_ordered_by_relevance():
    listed = client.post("/options/process", json={"challenge": "Flood"}).json()["options"]
    direct = [o["id"] for o in listed if o["suggested"]]
    assert set(direct) == {"Runoff", "ChannelFlow", "Infiltration"}
    assert [o["id"] for o in listed][:3] == direct              # directly connected ones first
    assert "Directly connected" in listed[0]["hint"]


def test_results_separate_data_availability_from_method_compatibility():
    body = client.post("/recommend", json={"challenge": "Flood", "available_variables": ["Precipitation"]}).json()
    scs = next(r for r in body["results"] if r["id"] == "SCS-CN")
    assert scs["availability"]["score"] == 1.0                  # its only required input is in hand
    assert 0 < scs["compatibility"]["score"] < 1                # but it covers part of the processes
    rain = next(i for i in scs["inputs"] if i["id"] == "Precipitation")
    assert rain["kind"] == "forcing" and rain["state"] == "have"
    venant = next(r for r in body["results"] if r["id"] == "Saint-VenantEquations1D")
    kinds = {i["id"]: i["kind"] for i in venant["inputs"]}
    assert kinds["Discharge"] == "boundary" and kinds["ChannelGeometry"] == "static"


def test_linear_reservoir_has_two_distinct_jobs():
    body = client.post("/recommend", json={"challenge": "Flood"}).json()
    reservoir = next(r for r in body["results"] if r["id"] == "LinearReservoir")
    views = {v["id"]: v for v in reservoir["roles"]}
    assert set(views) == {"Role_RunoffTransform", "Role_Baseflow"}
    assert [v["id"] for v in views["Role_RunoffTransform"]["delivers"]] == ["Discharge"]
    assert [v["id"] for v in views["Role_Baseflow"]["delivers"]] == ["BaseFlowContribution"]


# ---- several outputs, grouped actions, software and contributed variables ---------------
def test_several_outputs_are_judged_one_by_one_with_their_question():
    _, found = improve(["SCS-CN", "Clark-UH"], {**FLOOD, "outputs": ["FloodExtentMap", "PeakFlow"]})
    outputs = {o["id"]: o for o in found["diagnosis"]["outputs"]}
    assert outputs["PeakFlow"]["status"] == "delivered"
    assert outputs["FloodExtentMap"]["status"] == "needs_combination"
    assert all(o["question"] for o in outputs.values())
    blocked = [i["subject"] for i in found["diagnosis"]["issues"] if i["code"] == "OUTPUT_NEEDS_COMBINATION"]
    assert blocked == ["FloodExtentMap"]


def test_single_output_of_older_clients_still_works():
    _, old = improve(["Clark-UH"], {**FLOOD, "output": "FloodExtentMap"})
    _, new = improve(["Clark-UH"], {**FLOOD, "outputs": ["FloodExtentMap"]})
    assert old["diagnosis"]["fit"] == new["diagnosis"]["fit"]


def test_output_options_carry_the_question_they_answer():
    outputs = options("output", setup={"methods": ["Clark-UH"]}, context={"challenge": "Flood"})["options"]
    assert any(o["question"] for o in outputs)


def test_every_action_says_what_it_is_for_where_it_runs_and_what_it_brings():
    _, found = improve(["SCS-CN", "Clark-UH"], {**FLOOD, "outputs": ["FloodExtentMap"]})
    assert found["actions"]
    for action in found["actions"]:
        target = action["target"]
        assert target["type"] in {"data", "role", "process", "output", "method", "workflow", "component"}
        if target["type"] == "data":
            assert target["nature"] in {"forcing", "boundary", "static", "initial"}
        adds_method = "setup.methods+" in action["patch"] or "setup" in action["patch"]
        if adds_method:
            assert action["software"]["same"] in (True, False, None) and action["software"]["text"]
            assert action["contributes"] and all(c["variables"] for c in action["contributes"])
    extensions = [a for a in found["actions"] if a["kind"] == "extend_output"]
    assert extensions
    for action in extensions:
        uses = [v["use"] for c in action["contributes"] for v in c["variables"] if v["use"]]
        assert any("flood extent map" in use for use in uses)


# ---- the diagnosis page: the study, the chain as a picture, workflows by challenge --------
def test_diagnosis_repeats_the_study_and_links_the_methods():
    context = {**FLOOD, "outputs": ["PeakFlow"], "output_step": "Hourly"}
    _, found = improve(["SCS-CN", "Clark-UH", "Muskingum-Cunge"], context)
    d = found["diagnosis"]
    assert d["study"]["challenge"]["id"] == "Flood" and d["study"]["output_step"]["id"] == "Hourly"
    assert [m["id"] for m in d["setup"]["methods"]] == ["SCS-CN", "Clark-UH", "Muskingum-Cunge"]
    assert {(link["from"], link["to"]) for link in d["links"]} >= {("SCS-CN", "Clark-UH"), ("Clark-UH", "Muskingum-Cunge")}
    assert all(output["produced_by"] for output in d["outputs"] if output["status"] == "delivered")


def test_a_method_too_coarse_for_the_wanted_results_is_reported(k):
    finest = timesteps.order(k.hours, k.hours)[0]
    coarse = next(m for m in k.facts if chains.get(k, m, "supportsTimeStep") and chains.get(k, m, "fillsRole")
                  and not timesteps.can_deliver(k.hours, chains.get(k, m, "supportsTimeStep"), finest))
    body = {"setup": {"methods": [coarse]}, "context": {**FLOOD, "output_step": finest}, "data": []}
    response = client.post("/setup/diagnose", json=body)
    assert response.status_code == 200, response.text
    assert "OUTPUT_STEP" in codes(response.json())


def test_standard_workflows_say_which_challenges_they_serve():
    found = options("reference_chain")["options"]
    assert found and all(chain["challenges"] for chain in found)
    assert options("output_step")["options"]


# ---- how an output is obtained; where derived parameters come from ---------------------------
def test_outputs_are_traced_back_to_the_methods_and_derivations_are_explained():
    _, found = improve(["SCS-CN", "Clark-UH"], {**FLOOD, "outputs": ["FloodExtentMap", "PeakFlow"]})
    outputs = {o["id"]: o for o in found["diagnosis"]["outputs"]}
    assert outputs["PeakFlow"]["trace"][0]["computed_by"]
    assert outputs["FloodExtentMap"]["needs_grid"] and not outputs["FloodExtentMap"]["trace"][0]["computed_by"]
    rows = {r["id"]: r for r in found["diagnosis"]["data"]}
    way = rows["CurveNumber"]["derivations"][0]
    assert {i["id"] for i in way["from"]} == {"LandCover", "SoilTexture"} and way["how"]


def test_the_data_search_explains_derived_parameters():
    found = client.get("/datasets/search", params={"q": "curve number"}).json()
    assert [v["id"] for v in found["derived"]] == ["CurveNumber"]
    assert found["derived"][0]["derivations"][0]["how"]
    assert client.get("/datasets/suggestions").json()["derived"]
