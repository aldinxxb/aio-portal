"""Run with:  pytest      (from the backend folder). Needs GraphDB running with v0.8.0 loaded.

Entry 3, start from data: map layers, open data of the area, roles, readiness, next dataset.
The map layers are read from backend/cache/ (fetched and simplified once from Sandre / IGN).
"""
import pytest
from fastapi.testclient import TestClient

from app import geo, knowledge, opendata
from app.main import app

client = TestClient(app)
ADOUR_GARONNE = {"layer": "basins", "id": "FRF", "name": "Adour Garonne", "bbox": [-1.8, 42.7, 4.3, 46.4]}
DATA = [{"variable": "Precipitation", "step": "Daily", "start": 2000, "end": 2020, "form": "series"},
        {"variable": "Discharge", "step": "Daily", "start": 2005, "end": 2020, "form": "series"},
        {"variable": "DTM", "form": "map"}]


def assess(**body):
    response = client.post("/opendata/assess", json=body)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def k():
    return knowledge.load()


# ---- map layers --------------------------------------------------------------------------

@pytest.mark.parametrize("layer, count", [("basins", 9), ("subbasins", 34), ("regions", 13), ("departments", 96)])
def test_layers_are_light_and_in_metropolitan_france(layer, count):
    response = client.get(f"/geo/{layer}")
    found = response.json()
    assert len(found["features"]) == count
    for feature in found["features"]:
        box = feature["properties"]["bbox"]
        assert -5.6 <= box[0] and box[2] <= 10.0 and 41.2 <= box[1] and box[3] <= 51.2
    assert len(response.content) < 300_000


def test_unknown_layer_is_404():
    assert client.get("/geo/oceans").status_code == 404


def test_simplification_keeps_a_closed_ring():
    ring = [[0, 0], [1, 0.001], [2, 0], [2, 1], [1, 1.001], [0, 1], [0, 0]]
    assert len(geo.simplify(ring, 0.01)) == 5          # the two near-straight points are dropped


# ---- coverage of the area ------------------------------------------------------------------

def test_coverage_of_an_area(k):
    box = ADOUR_GARONNE["bbox"]
    assert opendata.coverage(k, ["Global"], box) == "full"
    assert opendata.coverage(k, ["France"], box) == "full"              # no box: by hierarchy
    assert opendata.coverage(k, ["MetropolitanFrance"], box) == "full"
    assert opendata.coverage(k, ["FrenchMountainMassifs"], box) == "partial"
    assert opendata.coverage(k, ["Global"], None) == "full"             # no area chosen


def test_discovered_open_data_covers_the_area():
    found = assess(area=ADOUR_GARONNE, data=DATA)
    assert found["supply"]["datasets"] >= 40
    assert all(d["coverage"] in ("full", "partial") for d in found["discovered"])
    era5 = next(d for d in found["discovered"] if d["id"] == "ERA5")
    assert era5["coverage"] == "full" and era5["period"] == "full"      # 1940 -> today covers 2000-2020


# ---- roles and readiness -----------------------------------------------------------------------

def test_data_roles():
    roles = {r["id"]: r for r in assess(area=ADOUR_GARONNE, data=DATA)["roles"]}
    assert roles["Precipitation"]["roles"] == ["forcing"]
    assert set(roles["Discharge"]["roles"]) == {"boundary", "calibration"}
    assert roles["DTM"]["roles"] == ["static"]
    assert roles["Precipitation"]["workflows"] > 5


def test_what_the_data_enables_is_sorted_by_readiness():
    enables = assess(area=ADOUR_GARONNE, data=DATA)["enables"]
    assert len(enables) == 6
    keys = [(e["hand"], e["area"]) for e in enables]
    assert keys == sorted(keys, reverse=True)
    assert all(e["hand"] + e["area"] + e["none"] == e["workflows"] for e in enables)


def test_objectives_and_outputs_reachable_first():
    found = assess(area=ADOUR_GARONNE, data=DATA, challenge="Flood", objective="Simulation")
    reach = [o["hand"] + o["area"] for o in found["objectives"]]
    assert reach == sorted(reach, reverse=True)
    outputs = found["outputs"]
    assert outputs[0]["suggested"] and outputs[0]["hand"] + outputs[0]["area"] > 0


def test_daily_rain_makes_hourly_flood_workflows_wait_for_finer_data():
    found = assess(area=ADOUR_GARONNE, data=DATA, challenge="Flood", objective="Simulation", outputs=["Hydrograph"])
    chains = found["workflows"]["chains"]
    order = [{"hand": 0, "area": 1, "none": 2}[c["readiness"]] for c in chains]
    assert order == sorted(order)                                         # runnable first
    assert any(c["readiness"] == "none" and any("finer time step" in r for r in c["reasons"]) for c in chains)
    assert any(n["finer"] for n in found["next_datasets"])                # finer rain is proposed


def test_adding_the_next_dataset_moves_workflows_forward():
    body = dict(area=ADOUR_GARONNE, data=DATA, challenge="Flood", objective="Simulation", outputs=["Hydrograph"])
    before = assess(**body)
    best = next(n for n in before["next_datasets"] if n["provides"])
    added = [{"variable": v["id"], "source": "dataset", "dataset": best["dataset"]["id"]} for v in best["provides"]]
    after = assess(**{**body, "data": DATA + added})

    def have(found):
        return sum(len([i for i in c["inputs"] if i["state"] == "have"]) for c in found["workflows"]["chains"])

    assert have(after) > have(before)


def test_declarable_variables_and_errors():
    variables = client.get("/opendata/variables").json()
    rain = next(v for v in variables if v["id"] == "Precipitation")
    assert rain["role"] == "forcing" and rain["datasets"] > 5
    bad = client.post("/opendata/assess", json={"data": [{"variable": "Nope"}]})
    assert bad.status_code == 422
