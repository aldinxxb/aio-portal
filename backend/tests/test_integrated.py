"""Run with:  pytest      (from the backend folder). Needs GraphDB running with v0.8.0 loaded,
plus ontology/aio-additions.ttl (the runoff-volume derivations).

Integrated software (MIKE SHE...): no overlapping proposal, and components that can be
left out with what is lost. The case is the one reported by the user: the MIKE SHE chain,
water availability, expected output "water balance".
"""
import pytest
from fastapi.testclient import TestClient

from app import knowledge, setup
from app.main import app

client = TestClient(app)

STUDY = {"challenge": "WaterAvailabilty", "objective": "Simulation", "outputs": ["WaterBalance"]}
MIKE_SHE = {"software": "MIKESHE", "reference_chain": "RC_MIKESHE_MIKE11", "methods": []}

# the MIKE SHE workflow WITH its optional components (interception, snow, actual ET)
MIKE_SHE_FULL = {"software": "MIKESHE", "reference_chain": "RC_MIKESHE_MIKE11",
                 "methods": ["Penman-Monteih", "RutterModel", "TemperatureIndexMethod", "RichardsEquation",
                             "KristenJensen", "DiffusiveWave2D", "FiniteDifferenceGroundwaterFlow",
                             "Saint-VenantEquations1D"]}


@pytest.fixture(scope="module")
def k():
    return knowledge.load()


def improve(setup_body, context=STUDY):
    response = client.post("/setup/improve", json={"setup": setup_body, "context": context, "data": []})
    assert response.status_code == 200, response.text
    return response.json()


def codes(found):
    return {i["code"] for i in found["diagnosis"]["issues"]}


# ---- the rules, on the ontology ---------------------------------------------------------

def test_integrated_methods_are_never_sliced(k):
    assert k.separability["GR4Jmodel"] == "integrated"       # always its four jobs together
    assert k.separability["RichardsEquation"] == "integrated"
    assert k.separability["LinearReservoir"] == "separable"  # baseflow alone in HEC-HMS
    assert k.separability["ShallowWaterEquations2D"] == "separable"
    taken = {"Role_SoilWaterBudget", "Role_ExcessRainfall", "Role_RunoffTransform"}
    assert setup.placement(k, "GR4Jmodel", "Role_Baseflow", taken) is None
    assert setup.placement(k, "GR4Jmodel", None, set()) == sorted(k.facts["GR4Jmodel"]["fillsRole"])
    assert setup.placement(k, "LinearReservoir", "Role_Baseflow", {"Role_RunoffTransform"}) == ["Role_Baseflow"]
    assert setup.placement(k, "ShallowWaterEquations2D", "Role_Hydraulics", {"Role_RunoffTransform"}) == ["Role_Hydraulics"]


def test_runoff_volume_derives_from_what_an_integrated_model_computes(k):
    reach, via = knowledge.closure(k, {"EffectiveRainfall"})
    assert "RunoffVolume" in reach and "integration" in via["RunoffVolume"]["method"]
    assert "RunoffVolume" not in knowledge.closure(k, {"Precipitation"})[0]


def test_a_software_has_one_module_per_job(k):
    modules = k.modules["MIKESHE"]
    assert "RichardsEquation" in modules["Role_SoilWaterBudget"]
    assert "DiffusiveWave2D" in modules["Role_RunoffTransform"]
    assert "GR4Jmodel" not in {m for methods in modules.values() for m in methods}


# ---- the reported case ------------------------------------------------------------------------

def test_mike_she_delivers_a_water_balance_without_another_model():
    found = improve(MIKE_SHE)
    assert found["diagnosis"]["fit"]["blocking"] == 0
    balance = found["diagnosis"]["outputs"][0]
    assert balance["status"] == "delivered"
    runoff = next(t for t in balance["trace"] if t["id"] == "RunoffVolume")
    assert runoff["computed_by"] == [] and runoff["derived"]["from"]      # derived, and said so
    assert not codes(found) & {"OUTPUT_NEEDS_COMBINATION", "NO_LINK", "OVERLAP"}
    added = [m for a in found["actions"] for m in a["patch"].get("setup.methods+", [])]
    assert "GR4Jmodel" not in added


def test_a_complete_model_forced_in_as_one_job_is_an_overlap():
    methods = [m["id"] for m in improve(MIKE_SHE)["diagnosis"]["setup"]["methods"]]
    found = improve({**MIKE_SHE, "methods": methods + ["GR4Jmodel"], "roles": {"GR4Jmodel": ["Role_Baseflow"]}})
    overlap = next(i for i in found["diagnosis"]["issues"] if i["code"] == "OVERLAP")
    assert overlap["subject"] == "GR4Jmodel" and "counted twice" in overlap["message"]


def test_missing_jobs_are_filled_from_the_software_itself(k):
    partial = {"software": "MIKESHE", "methods": ["Penman-Monteih", "RichardsEquation", "KristenJensen"]}
    found = improve(partial)
    added = [(a["kind"], m) for a in found["actions"] if a["kind"] in ("fill_role", "add_process", "extend_output", "feed_input")
             for m in a["patch"]["setup.methods+"]]
    assert added
    for kind, method in added:
        assert "MIKESHE" in k.facts[method]["canBeImplementedIn"], (kind, method)


def test_no_action_adds_a_method_into_a_job_already_done(k):
    for body, context in ((MIKE_SHE, STUDY),
                          ({"methods": ["SCS-CN", "Clark-UH", "Muskingum-Cunge"]},
                           {"challenge": "Flood", "objective": "Simulation", "outputs": ["FloodExtentMap"]})):
        found = improve(body, context)
        held = {r["id"] for m in found["diagnosis"]["setup"]["methods"] for r in m["roles"]}
        for action in found["actions"]:
            if "setup.methods-" in action["patch"] or "setup" in action["patch"]:
                continue                                    # a replacement, not an addition
            for method, jobs in action["patch"].get("setup.roles+", {}).items():
                assert not set(jobs) & held, (action["message"], jobs)
                assert not found_overlap(k, method, jobs)


def found_overlap(k, method, jobs):
    """Is the method integrated and given only part of its jobs?"""
    return k.separability[method] == "integrated" and set(jobs) != set(k.facts[method]["fillsRole"])


# ---- leaving a component out -------------------------------------------------------------------

def test_each_component_says_what_is_lost_without_it():
    found = improve(MIKE_SHE_FULL)
    parts = {c["id"]: c for c in found["components"]}
    assert set(parts) == {m["id"] for m in found["diagnosis"]["setup"]["methods"]}
    snow = parts["TemperatureIndexMethod"]
    assert [p["id"] for p in snow["loses"]["processes"]] == ["Snowmelt"] and snow["verdict"] != "costly"
    # the unsaturated zone is the heart of the water balance: leaving it out loses the output
    soil = parts["RichardsEquation"]
    assert soil["verdict"] == "costly" and [o["id"] for o in soil["loses"]["outputs"]] == ["WaterBalance"]
    # without the evapotranspiration demand, the modules after it need it as data
    pet = parts["Penman-Monteih"]
    needs = {(d["method"]["id"], d["variable"]["id"]) for d in pet["loses"]["downstream"]}
    assert ("KristenJensen", "PotentialEvapotranspiration") in needs
    assert all(d["then"] for d in pet["loses"]["downstream"])
    # a simpler module of the same software can replace the groundwater solver's neighbour
    assert "ConceptualRoutingReservoir" in [x["id"] for x in parts["Saint-VenantEquations1D"]["same_software"]]


def test_a_component_left_out_on_purpose_is_not_proposed_again():
    found = improve(MIKE_SHE_FULL)
    snow = next(c for c in found["components"] if c["id"] == "TemperatureIndexMethod")
    methods = [m["id"] for m in found["diagnosis"]["setup"]["methods"] if m["id"] != snow["id"]]
    after = improve({**MIKE_SHE, "methods": methods, "left_out": snow["patch"]["setup.left_out+"]})
    assert [m["id"] for m in after["diagnosis"]["setup"]["left_out"]] == ["TemperatureIndexMethod"]
    for action in after["actions"]:
        assert "TemperatureIndexMethod" not in action["patch"].get("setup.methods+", [])
        assert "TemperatureIndexMethod" not in action["patch"].get("setup", {}).get("methods", [])
    assert after["diagnosis"]["outputs"][0]["status"] == "delivered"      # the water balance survives


def test_a_left_out_main_process_stays_reported_but_is_not_refilled():
    found = improve(MIKE_SHE)
    aquifer = next(c for c in found["components"] if c["id"] == "FiniteDifferenceGroundwaterFlow")
    assert any(p["main"] for p in aquifer["loses"]["processes"])           # baseflow is a main process
    methods = [m["id"] for m in found["diagnosis"]["setup"]["methods"] if m["id"] != aquifer["id"]]
    after = improve({**MIKE_SHE, "methods": methods, "left_out": aquifer["patch"]["setup.left_out+"]})
    missing = [i for i in after["diagnosis"]["issues"] if i["code"] == "MISSING_PRIMARY_PROCESS"]
    assert missing and all(i["accepted"] and "on purpose" in i["message"] for i in missing)
    assert not [a for a in after["actions"] if a["kind"] == "add_process"]


# ---- the ontology states which methods are packages (aio:hasInseparableRoles) ---------------

def test_every_multi_role_method_is_stated_in_the_ontology(k):
    several = [m for m, facts in k.facts.items() if len(facts.get("fillsRole", [])) > 1]
    assert len(several) == 12
    assert all(k.separability_source[m] == "stated" for m in several)
    assert "unknown" not in {k.separability[m] for m in several}        # nothing left to guess


def test_the_four_methods_no_chain_used_are_now_decided(k):
    # (aio-software.ttl now uses three of them in workflows: the statement still decides)
    assert k.separability["KinematicWave"] == "separable"
    assert k.separability["SoilMoistureAccounting"] == "integrated"
    assert k.separability["VIC-RunoffGeneration"] == "integrated"
    assert k.separability["FiniteVolumeSedimentTransport"] == "integrated"


def test_kinematic_wave_can_be_proposed_for_one_job(k):
    # as the runoff transform, next to a method that already does the channel routing
    assert setup.placement(k, "KinematicWave", "Role_RunoffTransform", {"Role_ChannelRouting"}) == ["Role_RunoffTransform"]
    found = improve({"methods": ["SCS-CN", "Muskingum-Cunge"]}, {"challenge": "Flood", "objective": "Simulation"})
    transforms = [m for a in found["actions"] if a["kind"] == "fill_role" and a["subject"] == "Role_RunoffTransform"
                  for m in a["patch"]["setup.methods+"]]
    assert transforms                                    # a transform is proposed for the missing job
    for action in found["actions"]:
        for method, jobs in action["patch"].get("setup.roles+", {}).items():
            if method == "KinematicWave":
                assert jobs == ["Role_RunoffTransform"]


def test_a_package_is_never_proposed_for_one_job_and_is_flagged_when_forced(k):
    # Soil Moisture Accounting does the soil water budget AND the excess rainfall
    assert setup.placement(k, "SoilMoistureAccounting", "Role_SoilWaterBudget", {"Role_ExcessRainfall"}) is None
    assert setup.placement(k, "SoilMoistureAccounting", "Role_SoilWaterBudget", set()) == \
        ["Role_ExcessRainfall", "Role_SoilWaterBudget"]
    forced = improve({"methods": ["SCS-CN", "SoilMoistureAccounting", "Clark-UH"],
                      "roles": {"SoilMoistureAccounting": ["Role_SoilWaterBudget"]}},
                     {"challenge": "Flood", "objective": "Simulation"})
    overlap = [i for i in forced["diagnosis"]["issues"] if i["code"] == "OVERLAP"]
    assert overlap and overlap[0]["subject"] == "SoilMoistureAccounting"


def test_a_statement_in_the_ontology_wins_over_the_chains(k):
    # 2D diffusive wave is only ever a runoff transform in the chains, and stated separable;
    # Richards holds both its jobs in every chain, and stated a package: both agree here,
    # but the statement is what is read
    assert k.facts["RichardsEquation"]["hasInseparableRoles"] == ["true"]
    assert k.facts["DiffusiveWave2D"]["hasInseparableRoles"] == ["false"]
