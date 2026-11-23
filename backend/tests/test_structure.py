"""Run with:  pytest      (from the backend folder). Needs GraphDB running with v0.8.0 loaded,
plus ontology/aio-additions.ttl.

The three corrections made after the sweep, the alternatives inside a software, and the
Water Challenge entry using the same structure as the diagnosis.
"""
import pytest
from fastapi.testclient import TestClient

from app import knowledge, setup
from app.main import app

client = TestClient(app)
FLOOD = {"challenge": "Flood", "objective": "Simulation"}


@pytest.fixture(scope="module")
def k():
    return knowledge.load()


def improve(setup_body, context):
    response = client.post("/setup/improve", json={"setup": setup_body, "context": context, "data": []})
    assert response.status_code == 200, response.text
    return response.json()


def chains(**body):
    response = client.post("/chains", json=body)
    assert response.status_code == 200, response.text
    return response.json()["chains"]


# ---- 1. a standard coupling to another software stays proposed ------------------------------

def test_hec_ras_2d_is_still_proposed_next_to_hec_hms_own_option(k):
    found = improve({"software": "HEC-HMS", "methods": ["SCS-CN", "Clark-UH", "Muskingum-Cunge"]},
                    {**FLOOD, "outputs": ["FloodExtentMap"]})
    added = {m: a for a in found["actions"] if a["kind"] == "extend_output" for m in a["patch"]["setup.methods+"]}
    assert "DiffusiveWave2D" in added and added["DiffusiveWave2D"]["software"]["same"] is True
    # the usual practice: the hydrograph goes to HEC-RAS 2D, another software
    assert "ShallowWaterEquations2D" in added and added["ShallowWaterEquations2D"]["software"]["same"] is False
    # but a method of another software with no standard coupling is not proposed
    assert "ManningsEquation" not in added


# ---- 2. only derivations valid for model results deliver an output ------------------------------

def test_a_rating_curve_does_not_make_a_rainfall_runoff_chain_deliver_water_levels(k):
    assert any(not way["model"] for way in k.derivations["WaterLevel"])        # a data derivation
    assert "WaterLevel" not in knowledge.closure(k, {"Discharge"})[0]
    found = improve({"methods": ["SCS-CN", "Clark-UH"]}, {**FLOOD, "outputs": ["WaterLevelSeries"]})
    assert found["diagnosis"]["outputs"][0]["status"] == "needs_combination"


def test_runoff_volume_still_derives_from_model_results(k):
    assert all(way["model"] for way in k.derivations["RunoffVolume"])
    found = improve({"software": "MIKESHE", "reference_chain": "RC_MIKESHE_MIKE11", "methods": []},
                    {"challenge": "WaterAvailabilty", "objective": "Simulation", "outputs": ["WaterBalance"]})
    assert found["diagnosis"]["outputs"][0]["status"] == "delivered"


# ---- 3. no link warning between two steps of a standard chain -------------------------------------

def test_reference_chains_raise_no_link_or_overlap_warning(k):
    for chain in k.chains.values():
        template = k.templates[chain["template"]]
        request, _ = setup.normalise(k, setup.SetupRequest(
            setup=setup.Setup(reference_chain=chain["id"]),
            context=setup.Context(challenge=sorted(template["serves"])[0], objective="Simulation")))
        odd = [i["key"] for i in setup.diagnose(k, request)["issues"] if i["code"] in ("NO_LINK", "OVERLAP")]
        assert odd == [], (chain["id"], odd)


# ---- alternatives inside the same software, optional exchanges ---------------------------------------

def test_each_component_lists_the_other_methods_of_its_software(k):
    full = ["Penman-Monteih", "RutterModel", "TemperatureIndexMethod", "RichardsEquation", "KristenJensen",
            "DiffusiveWave2D", "FiniteDifferenceGroundwaterFlow", "Saint-VenantEquations1D"]
    found = improve({"software": "MIKESHE", "reference_chain": "RC_MIKESHE_MIKE11", "methods": full},
                    {"challenge": "WaterAvailabilty", "objective": "Simulation", "outputs": ["WaterBalance"]})
    parts = {c["id"]: c for c in found["components"]}
    et = parts["KristenJensen"]["alternatives"]
    assert {x["id"] for x in et} >= {"RootzoneStress", "MoistureContentThresholds"}
    for x in et:
        assert "MIKESHE" in k.facts[x["id"]]["canBeImplementedIn"]
        assert [r["id"] for r in x["roles"]] == ["Role_ActualET"]              # the same job
        assert x["patch"]["setup.methods-"] == ["KristenJensen"] and "fit_after" in x
    # accepting one keeps the set-up consistent
    body = {"setup": {"software": "MIKESHE", "methods": [m["id"] for m in found["diagnosis"]["setup"]["methods"]],
                      "roles": {m["id"]: [r["id"] for r in m["roles"]] for m in found["diagnosis"]["setup"]["methods"]}},
            "context": {"challenge": "WaterAvailabilty", "objective": "Simulation", "outputs": ["WaterBalance"]}, "data": []}
    swap = et[0]["patch"]
    body["setup"]["methods"] = [m for m in body["setup"]["methods"] if m not in swap["setup.methods-"]] + swap["setup.methods+"]
    body["setup"]["roles"].update(swap["setup.roles+"])
    after = client.post("/setup/diagnose", json=body).json()
    assert after["fit"]["blocking"] == 0 and after["fit"]["score"] == et[0]["fit_after"]


def test_links_say_which_exchanges_are_optional():
    found = improve({"software": "MIKESHE", "reference_chain": "RC_MIKESHE_MIKE11", "methods": []},
                    {"challenge": "WaterAvailabilty", "objective": "Simulation"})
    links = found["diagnosis"]["links"]
    assert all({"optional", "optional_only"} <= set(link) for link in links)
    assert any(link["optional_only"] for link in links) and any(not link["optional_only"] for link in links)


# ---- the Water Challenge entry uses the same structure -------------------------------------------------

def test_mike_she_is_proposed_for_a_water_balance():
    found = [c["id"] for c in chains(challenge="WaterAvailabilty", outputs=["WaterBalance"]) if c["kind"] == "reference"]
    assert "RC_MIKESHE_MIKE11" in found and "RC_SWAT_ContinuousWB" in found


def test_a_chosen_software_keeps_only_its_workflows(k):
    found = chains(challenge="Flood", software="HEC-HMS")
    assert found and all("HEC-HMS" in [s["id"] for s in c["software"]] for c in found if c["kind"] == "reference")
    for chain in found:
        if chain["kind"] == "generated":
            for step in chain["steps"]:
                assert "HEC-HMS" in k.facts[step["method"]["id"]]["canBeImplementedIn"]
    assert client.post("/chains", json={"challenge": "Flood", "software": "Excel"}).status_code == 422


def test_generated_chains_never_slice_a_package(k):
    for challenge in ("Flood", "WaterAvailabilty", "Drought"):
        for chain in chains(challenge=challenge):
            if chain["kind"] != "generated":
                continue
            for step in chain["steps"]:
                method = step["method"]["id"]
                if k.separability[method] == "integrated":
                    template_roles = {s["role"] for s in k.templates[chain["template"]["id"]]["slots"]}
                    expected = set(k.facts[method]["fillsRole"]) & template_roles
                    assert {r["id"] for r in step["roles"]} == expected, (chain["id"], method)


# ---- essential and optional components, software modules, outputs-driven processes -----------

def test_a_standard_workflow_starts_with_its_essential_components(k):
    found = improve({"software": "MIKESHE", "reference_chain": "RC_MIKESHE_MIKE11", "methods": []},
                    {"challenge": "WaterAvailabilty", "objective": "Simulation", "outputs": ["WaterBalance"]})
    methods = {m["id"]: m for m in found["diagnosis"]["setup"]["methods"]}
    assert set(methods) == {"Penman-Monteih", "RichardsEquation", "DiffusiveWave2D",
                            "FiniteDifferenceGroundwaterFlow", "Saint-VenantEquations1D"}
    assert all(m["essential"] for m in methods.values())
    assert found["diagnosis"]["fit"]["blocking"] == 0
    # the optional ones are recommended, each saying what it adds
    optional = {a["proposal"]["method"]["id"]: a for a in found["actions"] if a["kind"] == "add_component"}
    assert set(optional) == {"RutterModel", "TemperatureIndexMethod", "KristenJensen"}
    assert optional["TemperatureIndexMethod"]["proposal"]["adds_processes"][0]["id"] == "Snowmelt"
    assert all(a["group"] == "optional" and a["standard_practice"] for a in optional.values())


def test_methods_say_which_module_of_the_software_they_are(k):
    found = improve({"software": "MIKESHE", "reference_chain": "RC_MIKESHE_MIKE11", "methods": []},
                    {"challenge": "WaterAvailabilty", "objective": "Simulation"})
    richards = next(m for m in found["diagnosis"]["setup"]["methods"] if m["id"] == "RichardsEquation")
    assert richards["runs_in"]["id"] == "MIKESHE"
    assert "Unsaturated zone" in richards["module"]["name"] and "≤ 2 h" in richards["module"]["time_step"]
    river = next(m for m in found["diagnosis"]["setup"]["methods"] if m["id"] == "Saint-VenantEquations1D")
    assert river["runs_in"]["id"] == "MIKE11" and river["module"]["resolution"]


def test_workflows_show_essential_steps_and_optional_ones_with_resolution():
    chain = next(c for c in chains(challenge="WaterAvailabilty", outputs=["WaterBalance"]) if c["id"] == "RC_MIKESHE_MIKE11")
    assert {s["method"]["id"] for s in chain["steps"]} == {"Penman-Monteih", "RichardsEquation", "DiffusiveWave2D",
                                                         "FiniteDifferenceGroundwaterFlow", "Saint-VenantEquations1D"}
    assert all(s["module"] for s in chain["steps"])
    assert {o["method"]["id"] for o in chain["optional_steps"]} == {"RutterModel", "TemperatureIndexMethod", "KristenJensen"}


def test_workflows_from_several_software_and_couplings():
    found = chains(challenge="Flood", outputs=["FloodExtentMap"])
    software = {s["id"] for c in found for s in c["software"]}
    assert {"HEC-HMS", "HEC-RAS", "SWAT", "TELEMAC-2D", "MIKESHE", "MIKE21", "SWMM", "IberPlus"} <= software
    coupled = [c for c in found if len(c["software"]) > 1]
    assert len(coupled) >= 4


def test_outputs_replace_the_process_step():
    body = client.post("/recommend", json={"challenge": "Flood", "outputs": ["FloodExtentMap"]}).json()
    assert body["urr"]["processes"]["source"] == "outputs"
    related = {p["id"] for p in body["related_processes"]["values"]}
    assert {"Runoff", "ChannelFlow", "Infiltration"} <= related
    assert body["related_entities"] and "River" in {e["id"] for e in body["related_entities"]}
    extent = body["expected_outputs"][0]
    assert extent["question"] and extent["forms"][0]["id"] == "MapForm"
    level = extent["variables"][0]
    assert level["id"] == "WaterLevel" and level["count"] > 0 and level["computed_by"]
