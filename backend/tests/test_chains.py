"""Run with:  pytest      (from the backend folder). Needs GraphDB running with v0.8.0 loaded.

Ontology 0.8.0: time-step aggregation and method chains. The expected values come from
the backend specification (sections 1.4, 2.6 and 3).
"""
import pytest
from fastapi.testclient import TestClient

from app import chains, knowledge, timesteps
from app.main import app

client = TestClient(app)

HOURS = {"SubHourly": 0.0, "Hourly": 1.0, "Daily": 24.0, "MonthlyOrLonger": 720.0}


@pytest.fixture(scope="module")
def k():
    return knowledge.load()


def post(path: str, **body):
    response = client.post(path, json=body)
    assert response.status_code == 200, response.text
    return response.json()


# ---- time-step rules, no database ---------------------------------------------

def test_fine_data_can_feed_a_coarser_method_but_not_the_reverse():
    assert timesteps.usable_as_is(HOURS, ["Daily"], "Hourly") is True       # aggregate the data
    assert timesteps.usable_as_is(HOURS, ["Hourly", "SubHourly"], "Daily") is False
    assert timesteps.usable_as_is(HOURS, [], "Daily") is True               # nothing recorded


def test_a_finer_method_can_deliver_coarser_results():
    assert timesteps.can_deliver(HOURS, ["SubHourly"], "Hourly") is True
    assert timesteps.can_deliver(HOURS, ["Daily"], "Hourly") is False


def test_static_data_always_passes_and_coarse_data_does_not():
    assert timesteps.dataset_ok(HOURS, None, ["Hourly"]) is True            # a DEM has no time step
    assert timesteps.dataset_ok(HOURS, "Daily", ["Hourly"]) is False
    assert timesteps.dataset_ok(HOURS, "SubHourly", ["Hourly"]) is True


def test_upstream_method_must_run_at_least_as_finely():
    assert timesteps.step_ok(HOURS, ["Hourly", "Daily"], ["Hourly"]) is True
    assert timesteps.step_ok(HOURS, ["Daily"], ["Hourly", "SubHourly"]) is False


# ---- time steps with the ontology (spec 1.4) -----------------------------------

def test_daily_data_never_makes_a_sub_daily_method_usable_as_is(k):
    runoff = [m for m in k.facts if "Runoff" in chains.get(k, m, "modelsProcess")]
    usable = {m for m in runoff
              if timesteps.usable_as_is(k.hours, chains.get(k, m, "supportsTimeStep"), "Daily")}
    assert usable == {"ConceptualRoutingReservoir", "GR4Jmodel", "LinearReservoir",
                      "NonLinearReservoir", "SCS-CN", "VIC-RunoffGeneration"}
    assert set(runoff) - usable == {"Clark-UH", "DiffusiveWave2D", "KinematicWave", "ModClark",
                                    "SCS-UH", "ShallowWaterEquations2D"}


def test_only_hourly_or_finer_rain_is_fine_enough_for_modclark(k):
    supports = chains.get(k, "ModClark", "supportsTimeStep")
    fine = {s["dataset"] for s in k.data["Precipitation"]
            if s["dataset"] and s["step"] and timesteps.dataset_ok(k.hours, s["step"], supports)}
    assert fine == {"ERA5", "ERA5-Land", "IMERG", "PackageRadar"}


def test_hourly_results_include_hourly_and_sub_hourly_methods(k):
    body = post("/recommend", challenge="Flood", time_steps=["Hourly"])
    assert body["results"]
    for result in body["results"]:
        supports = chains.get(k, result["id"], "supportsTimeStep")
        assert timesteps.can_deliver(k.hours, supports, "Hourly")
    ids = {r["id"] for r in body["results"]}
    assert "KinematicWave" in ids                      # sub-hourly / hourly method: kept
    assert body["filtered_out"] > 0                    # daily-only methods: hidden


def test_daily_data_puts_methods_needing_disaggregation_last():
    body = post("/recommend", challenge="Flood", data_time_step="Daily")
    flags = [r["time_step"]["needs_disaggregation"] for r in body["results"]]
    assert True in flags and False in flags
    assert flags == sorted(flags)                      # usable ones first, none removed
    clark = next(r for r in body["results"] if r["id"] == "Clark-UH")
    assert clark["time_step"]["needs_disaggregation"]
    assert "finer time step" in clark["time_step"]["notes"][0]


def test_time_step_options_count_finer_methods_too():
    wanted = {o["id"]: o for o in post("/options/timestep", challenge="Flood")["options"]}
    assert list(wanted) == ["SubHourly", "Hourly", "Daily", "MonthlyOrLonger"]   # finest first
    assert wanted["SubHourly"]["count"] <= wanted["Hourly"]["count"] <= wanted["Daily"]["count"]
    data = {o["id"]: o for o in post("/options/datastep", challenge="Flood")["options"]}
    assert data["SubHourly"]["count"] >= data["Daily"]["count"]   # finer data suits more methods


def test_unknown_time_step_is_422():
    bad = client.post("/recommend", json={"challenge": "Flood", "data_time_step": "Weekly"})
    assert bad.status_code == 422


# ---- chains (spec 2.6 and 3) ----------------------------------------------------

def test_only_the_sediment_workflows_are_blocked_by_data(k):
    # 12 workflows of ontology 0.8.0 (10 runnable) + 12 from aio-software.ttl
    verdicts = {
        c["id"]: chains.evaluate(k, c["steps"], chains.context(), None, c["covers"], c["coupling"])
        for c in k.chains.values()
    }
    assert len(verdicts) == 24
    blocked = {i: v["missing"] for i, v in verdicts.items() if v["status"] != chains.RUNNABLE}
    assert blocked == {
        "RC_HECRAS_1DSediment": ["GrainSize", "SedimentPorosity"],
        "RC_Iber_2DSediment": ["CriticalShearStress", "GrainSize", "SedimentPorosity"],
        "RC_TELEMAC2D_GAIA": ["GrainSize", "SedimentPorosity"],   # a real data gap, reported
    }


def test_initial_conditions_are_not_missing_data(k):
    chain = k.chains["RC_SWAT_MODFLOW"]
    verdict = chains.evaluate(k, chain["steps"], chains.context(), None, chain["covers"], chain["coupling"])
    initial = {i["id"] for i in verdict["initial_conditions"]}
    assert initial and not (initial & set(verdict["missing"]))
    assert not (initial & {i["id"] for i in verdict["inputs"]})


def test_flood_extent_map_gives_the_inundation_workflows_with_a_2d_model(k):
    found = post("/chains", challenge="Flood", outputs=["FloodExtentMap"])
    reference = {c["id"] for c in found["chains"] if c["kind"] == "reference"}
    assert {"RC_HMS_RAS2D_Inundation", "RC_SWAT_TELEMAC2D_Inundation", "RC_RAS2D_RainOnGrid",
            "RC_MIKESHE_MIKEFLOOD", "RC_SWMM_Iber_DualDrainage"} <= reference
    assert "RC_HMS_RAS1D_Inundation" not in reference          # 1D: water levels, not a map
    for chain in found["chains"]:                              # every one has a gridded method
        assert any("FullyDistributed" in k.facts[s["method"]["id"]].get("hasSpatialRepresentation", [])
                   for s in chain["steps"])


def test_a_1d_river_model_gives_water_levels():
    found = post("/chains", challenge="Flood", outputs=["WaterLevelSeries"])
    assert "RC_HMS_RAS1D_Inundation" in {c["id"] for c in found["chains"]}


def test_open_source_filter_on_flood():
    found = post("/chains", challenge="Flood", licence="open")
    reference = [c["id"] for c in found["chains"] if c["kind"] == "reference"]
    assert "RC_SWAT_TELEMAC2D_Inundation" in reference and "RC_HMS_RAS2D_Inundation" not in reference
    assert all(c["all_open"] for c in found["chains"])


def test_generated_chains_are_labelled_and_never_outrank_a_runnable_reference():
    found = post("/chains", challenge="Flood")["chains"]
    generated = [c for c in found if c["kind"] == "generated"]
    assert generated and all("not a standard practice" in c["note"] for c in generated)
    assert all(c["status"] == "runnable" for c in generated)
    first_generated = found.index(generated[0])
    runnable_reference = [i for i, c in enumerate(found)
                          if c["kind"] == "reference" and c["status"] == "runnable"]
    assert max(runnable_reference) < first_generated


def test_daily_data_flags_the_step_and_proposes_a_replacement():
    found = post("/chains", challenge="Flood", data_time_step="Daily")["chains"]
    inundation = next(c for c in found if c["id"] == "RC_HMS_RAS2D_Inundation")
    assert inundation["status"] == "check"
    assert "finer time step" in " ".join(inundation["reasons"])
    step = next(s for s in inundation["steps"] if s["issue"])
    assert step["alternatives"]                        # a method doing the same job that fits
    assert found[0]["status"] == "runnable"            # usable chains still come first


def test_a_step_opens_on_inputs_parameters_and_outputs():
    chain = post("/chains", challenge="Flood")["chains"][0]
    for step in chain["steps"]:
        assert {"mandatory_inputs", "physical_parameters", "calibration_parameters",
                "outputs"} <= set(step["detail"])
    # an input produced by an earlier step is marked as coming from inside the chain
    states = {i["state"] for s in chain["steps"] for i in s["detail"]["mandatory_inputs"]}
    assert "internal" in states


def test_a_multi_role_method_is_one_step():
    found = post("/chains", challenge="Drought")["chains"]
    gr4j = next(c for c in found if c["id"] == "RC_GR4J_Daily")
    step = next(s for s in gr4j["steps"] if s["method"]["id"] == "GR4Jmodel")
    assert len(step["roles"]) == 4 and len(gr4j["steps"]) == 2


def test_unknown_licence_is_422():
    bad = client.post("/chains", json={"challenge": "Flood", "licence": "cheap"})
    assert bad.status_code == 422


# ---- one method: what it combines with ------------------------------------------

def test_transform_method_alone_is_not_runnable_but_names_its_feeders():
    found = post("/methods/Clark-UH/combine", software="HEC-HMS")
    assert found["alone"]["status"] == "check"         # it needs effective rainfall from a loss method
    assert "SCS-CN" in {n["id"] for n in found["fed_by"]}
    rain = next(i for i in found["inputs"] if i["id"] == "EffectiveRainfall")
    assert "SCS-CN" in {p["id"] for p in rain["producers"]}
    assert found["fed_by"][0]["same_software"] is True  # same software first
    assert "RC_HMS_EventFlood" in {c["id"] for c in found["chains"]}


def test_complete_model_is_recognised():
    assert post("/methods/GR4Jmodel/combine")["complete_model"] is True
    assert post("/methods/SCS-CN/combine")["complete_model"] is False


def test_datasets_of_an_input_say_if_they_are_fine_enough():
    # ModClark runs hourly or finer: the daily effective-rainfall products are too coarse
    found = post("/methods/ModClark/combine")
    rain = next(i for i in found["inputs"] if i["id"] == "EffectiveRainfall")
    assert rain["datasets"] and not any(d["fine_enough"] for d in rain["datasets"])
    # GR4J runs daily: every precipitation dataset is fine enough (finer data is aggregated)
    found = post("/methods/GR4Jmodel/combine")
    rain = next(i for i in found["inputs"] if i["id"] == "Precipitation")
    assert rain["datasets"] and all(d["fine_enough"] for d in rain["datasets"])


def test_combine_unknown_method_is_404():
    assert client.post("/methods/NoSuchMethod/combine", json={}).status_code == 404


# ---- data entry and dataset search ----------------------------------------------

def test_reach_says_what_to_add_next_and_which_workflows():
    reached = post("/reach", available_variables=["Precipitation"])["challenges"]
    flood = next(c for c in reached if c["id"] == "Flood")
    assert flood["workflows"] and flood["workflows"][0]["methods"]
    assert all({"id", "unlocks", "open_data"} <= set(n) for n in flood["next_data"])
    assert all("outputs" in d and "software" in d for d in flood["direct"])


def test_search_by_dataset_name_lists_all_its_variables():
    found = client.get("/datasets/search", params={"q": "era5 land"}).json()["datasets"]
    land = next(d for d in found if d["id"] == "ERA5-Land")
    assert land["matched_by"] == "dataset" and len(land["provides"]) > 10
    by_variable = client.get("/datasets/search", params={"q": "precipitation"}).json()["datasets"]
    era5 = next(d for d in by_variable if d["id"] == "ERA5")
    assert era5["matched_by"] == "variable"            # only its matching variables are listed
    assert all("precipitation" in (v["label"] or "").lower() for v in era5["provides"])


def test_search_suggestions_have_variables_and_datasets():
    found = client.get("/datasets/suggestions").json()
    assert "ERA5" in {d["id"] for d in found["datasets"]}
    assert "Precipitation" in {v["id"] for v in found["variables"]}


def test_deprecated_entity_name_is_translated():
    body = post("/recommend", challenge="Flood", entity="Catchement")
    assert body["urr"]["entity"] == "Catchment"
