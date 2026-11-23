"""Entry 3, "Start from data": what can I do with the data I have, here?

The flow (see the flowchart in docs):
  1. locate the study area                    (user: map, region, water entity)
  2. declare the data in hand                 (user: variable, time step, period, form)
     + discover open data covering the area   (system)
  3. classify the data roles                  (system: forcing, boundary, static, calibration, initial)
  4. show what the data enables               (system: challenges, outputs, readiness)
  5. pick challenge and objective             (user: reachable options first)
  6. confirm expected output                  (user: suggested from data and goal)
  7. recommend runnable workflows             (system)
     + the next dataset to add                (system: adding it re-runs from step 3)

One call (assess) computes everything the answers given so far allow.

Readiness of a workflow, for this user and this area:
  ready with your data      every input and parameter it needs is in hand
  ready with open data      what is not in hand is given by open data COVERING THE AREA
  not ready                 something has no source here

Layering: opendata.py -> knowledge.py, chains.py, ontology.py, timesteps.py, requirements.py.
"""
import re
from types import SimpleNamespace

from pydantic import BaseModel, Field

from app import chains, knowledge, ontology, requirements, timesteps
from app.chains import get, ref, refs

METROPOLITAN = "MetropolitanFrance"


class Area(BaseModel):
    layer: str | None = None                  # basins, subbasins, regions, departments
    id: str | None = None
    name: str | None = None
    bbox: list[float] | None = None           # [min lon, min lat, max lon, max lat]


class DataItem(BaseModel):
    variable: str
    source: str = "own"                       # own | dataset
    dataset: str | None = None
    step: str | None = None                   # SubHourly, Hourly, Daily, MonthlyOrLonger
    start: int | None = None                  # first year
    end: int | None = None                    # last year
    form: str | None = None                   # series | map | points | static


class AssessRequest(BaseModel):
    area: Area | None = None
    entity: str | None = None
    data: list[DataItem] = Field(default_factory=list)
    challenge: str | None = None
    objective: str | None = None
    outputs: list[str] = Field(default_factory=list)


# ----------------------------------------------------------------------------
# Geography of the catalogue: which datasets cover the chosen area
# ----------------------------------------------------------------------------

def parse_box(wkt: str | None) -> list[float] | None:
    if not wkt:
        return None
    numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", wkt)]
    xs, ys = numbers[0::2], numbers[1::2]
    return [min(xs), min(ys), max(xs), max(ys)] if xs else None


_areas: dict[int, dict] = {}


def catalogue_areas(k) -> dict[str, dict]:
    """Every geographic area of the catalogue: bounding box and the areas it lies within."""
    if id(k) not in _areas:
        found = {}
        for area, values in ontology.describe("GeographicArea").items():
            found[area] = {"box": parse_box(next(iter(values.get("bbox", [])), None)),
                           "within": set(values.get("isWithin", []))}
        _areas.clear()
        _areas[id(k)] = found
    return _areas[id(k)]


def contains(outer: list[float], inner: list[float]) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def intersects(a: list[float], b: list[float]) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def coverage(k, area_ids: list[str], box: list[float] | None) -> str | None:
    """How a dataset's areas cover the chosen area: "full", "partial" or None.

    With a bounding box: contains = full, overlaps = partial. Without one (France,
    French mountain massifs...): the hierarchy decides. The chosen area is always in
    metropolitan France, so an area containing metropolitan France covers it fully, and
    an area inside metropolitan France covers it only in part.
    """
    if box is None:
        return "full" if area_ids else None
    areas = catalogue_areas(k)
    best = None
    for area in area_ids:
        info = areas.get(area, {"box": None, "within": set()})
        if info["box"]:
            if contains(info["box"], box):
                return "full"
            if intersects(info["box"], box):
                best = "partial"
        elif area in areas.get(METROPOLITAN, {}).get("within", set()):
            return "full"                       # France, Europe...: they contain metropolitan France
        elif METROPOLITAN in info["within"]:
            best = best or "partial"            # a part of metropolitan France (mountain massifs...)
    return best


def discover(k, area: Area | None, period: tuple[int, int] | None) -> list[dict]:
    """Every catalogued dataset covering the area, best coverage and most variables first."""
    box = area.bbox if area and area.bbox else None
    found = []
    for dataset in ontology.list_datasets():
        cover = coverage(k, [a["id"] for a in dataset["coverage"]], box)
        if cover is None:
            continue
        sources = [s for v in dataset["variables"] for s in k.data.get(v["id"], []) if s["dataset"] == dataset["id"]]
        provenance = sorted({s["provenance"] for s in sources if s["provenance"]})
        in_period = None
        if period and dataset["start"]:
            first = int(dataset["start"][:4])
            last = 9999 if dataset["ongoing"] else int(dataset["end"][:4]) if dataset["end"] else 9999
            in_period = "full" if first <= period[0] and last >= period[1] else \
                "partial" if first <= period[1] and last >= period[0] else "none"
        found.append({
            "id": dataset["id"], "label": dataset["label"], "url": dataset["url"],
            "publishers": dataset["publishers"], "areas": dataset["coverage"], "coverage": cover,
            "start": dataset["start"], "end": dataset["end"], "ongoing": dataset["ongoing"],
            "temporal_nature": dataset["temporal_nature"], "provenance": [ref(k, p) for p in provenance],
            "measured": any(p in knowledge.MEASURED for p in provenance),
            "period": in_period,
            "variables": [{"id": v["id"], "label": v["label"], "time_steps": v["time_steps"], "grids": v["grids"]}
                          for v in dataset["variables"]],
        })
    found.sort(key=lambda d: (d["coverage"] != "full", -len(d["variables"]), d["label"] or d["id"]))
    return found


def area_supply(k, discovered: list[dict]) -> tuple[set[str], set[str], dict[str, list[str]]]:
    """What open data gives in the area: variables (with derivations), measured ones, by dataset."""
    full = {d["id"] for d in discovered if d["coverage"] == "full"}
    variables: set[str] = set()
    measured: set[str] = set()
    providers: dict[str, list[str]] = {}
    for variable, sources in k.data.items():
        for source in sources:
            if source["dataset"] in full:
                variables.add(variable)
                providers.setdefault(variable, []).append(source["dataset"])
                if source["provenance"] in knowledge.MEASURED:
                    measured.add(variable)
    changed = True                               # derivations from what the area offers
    while changed:
        changed = False
        for variable, ways in k.derivations.items():
            if variable not in variables and any(way["inputs"] <= variables for way in ways):
                variables.add(variable)
                changed = True
    return variables, measured, providers


# ----------------------------------------------------------------------------
# Step 3: the role each piece of data plays
# ----------------------------------------------------------------------------

ROLE_TEXT = {
    "forcing": "forcing", "boundary": "boundary condition", "static": "static description",
    "calibration": "calibration", "initial": "initial state", "unused": "not used by any method",
}


def roles_of(k, variable: str) -> list[str]:
    """Every role a variable can play for the methods of the ontology."""
    found = []
    takes = any(variable in get(k, m, "requiresMandatoryInput") or variable in get(k, m, "acceptsOptionalInput")
                or variable in get(k, m, "hasPhysicalParameter") for m in k.facts)
    if takes:
        found.append(chains.input_kind(k, variable))
    if any(variable in get(k, m, "isCalibratedAgainst") for m in k.facts):
        found.append("calibration")
    if any(variable in get(k, m, "requiresInitialCondition") for m in k.facts):
        found.append("initial")
    return found or ["unused"]


def classify(k, data: list[DataItem]) -> list[dict]:
    rows = []
    for item in data:
        roles = roles_of(k, item.variable)
        users = [m for m in k.facts if item.variable in set(get(k, m, "requiresMandatoryInput"))
                 | set(get(k, m, "acceptsOptionalInput")) | set(get(k, m, "hasPhysicalParameter"))
                 | set(get(k, m, "isCalibratedAgainst")) | set(get(k, m, "requiresInitialCondition"))]
        workflows = [c["id"] for c in k.chains.values() if {s["method"] for s in c["steps"]} & set(users)]
        rows.append({
            **ref(k, item.variable), "role": roles[0], "roles": roles,
            "roles_text": [ROLE_TEXT[r] for r in roles],
            "methods": len(users), "workflows": len(workflows),
            "source": item.source, "dataset": ref(k, item.dataset) if item.dataset else None,
            "step": ref(k, item.step) if item.step else None, "start": item.start, "end": item.end,
            "form": item.form,
        })
    return rows


# ----------------------------------------------------------------------------
# Steps 4-7: readiness of the workflows
# ----------------------------------------------------------------------------

def readiness(chain: dict) -> str:
    """hand: everything in hand; area: the rest from open data of the area; none: not runnable here."""
    if chain["status"] != chains.RUNNABLE:
        return "none"
    states = {i["state"] for i in chain["inputs"]}
    return "hand" if states <= {"have"} else "area"


def modes_of(objective: str | None) -> list[set[str]]:
    """Hard temporal-mode requirements of a study objective (forecasting -> continuous)."""
    if not objective:
        return []
    return [set(r["allowed_values"]) for r in ontology.requirements_of(objective)
            if r["kind"] == "method" and r["strength"] == "hard" and r["on_property"] == "hasTemporalMode"]


def assess(k, body: AssessRequest) -> dict:
    hand = {d.variable for d in body.data}
    years = [y for d in body.data for y in (d.start, d.end) if y]
    period = (min(years), max(years)) if years else None
    discovered = discover(k, body.area, period)
    supply, measured, providers = area_supply(k, discovered)

    # the coarsest time step among the forcing data in hand (worst case for rule A)
    steps = [d.step for d in body.data if d.step and d.step in k.hours and roles_of(k, d.variable)[0] == "forcing"]
    data_step = max(steps, key=lambda s: k.hours[s]) if steps else None

    def context(objective: str | None = None):
        return chains.context(available=hand, data_step=data_step, modes=modes_of(objective),
                              obtainable=supply, measured=measured)

    result: dict = {
        "area": body.area.model_dump() if body.area else None,
        "discovered": discovered,
        "supply": {"variables": len(supply), "datasets": len(discovered),
                   "full": sum(1 for d in discovered if d["coverage"] == "full")},
        "roles": classify(k, body.data),
        "data_step": ref(k, data_step),
    }

    # ---- step 4: what the data enables, challenge by challenge ----------------------
    enables = []
    for challenge in sorted(k.challenges, key=lambda c: k.labels.get(c, c)):
        found = chains.recommend(k, challenge, [], context(), generated=0)["chains"]
        counts = {"hand": 0, "area": 0, "none": 0}
        outputs: dict[str, str] = {}
        for c in found:
            level = readiness(c)
            counts[level] += 1
            for o in c["delivers"]:
                if level != "none" and outputs.get(o["id"]) != "hand":
                    outputs[o["id"]] = level
        enables.append({
            **ref(k, challenge), "workflows": len(found), **counts,
            "outputs": [{**ref(k, o), "level": level} for o, level in sorted(outputs.items(), key=lambda x: x[1] != "hand")],
            "best": next((c["label"] for c in found if readiness(c) == "hand"), None)
                    or next((c["label"] for c in found if readiness(c) == "area"), None),
        })
    enables.sort(key=lambda e: (-e["hand"], -e["area"], e["label"] or e["id"]))
    result["enables"] = enables

    if not body.challenge:
        return result

    # ---- step 5: objectives, reachable first ---------------------------------------
    objectives = []
    for objective in sorted(k.vocabulary["objective"], key=lambda o: k.labels.get(o, o)):
        found = chains.recommend(k, body.challenge, [], context(objective), generated=0)["chains"]
        levels = [readiness(c) for c in found]
        objectives.append({**ref(k, objective), "hand": levels.count("hand"), "area": levels.count("area"),
                           "workflows": len(found)})
    objectives.sort(key=lambda o: (-(o["hand"] + o["area"]), -o["hand"], o["label"] or o["id"]))
    result["objectives"] = objectives

    # ---- step 6: outputs suggested from the data and the goal --------------------------
    found = chains.recommend(k, body.challenge, [], context(body.objective), generated=0)["chains"]
    typical = {o["id"]: o for o in ontology.list_outputs(body.challenge)}
    suggestions = []
    for output in typical.values():
        delivering = [c for c in found if any(d["id"] == output["id"] for d in c["delivers"])]
        levels = [readiness(c) for c in delivering]
        suggestions.append({
            **ref(k, output["id"]), "question": output["question"], "primary": output["primary"],
            "hand": levels.count("hand"), "area": levels.count("area"), "workflows": len(delivering),
            "variables": refs(k, k.output_variables.get(output["id"], set())),
            "entity_match": bool(body.entity) and body.entity in output["entities"],
        })
    suggestions.sort(key=lambda s: (-(s["hand"] * 10 + s["area"]), not s["entity_match"], not s["primary"],
                                    s["label"] or s["id"]))
    best = next((s for s in suggestions if s["hand"] + s["area"] > 0), None)
    for s in suggestions:
        s["suggested"] = best is not None and s["id"] == best["id"]
    result["outputs"] = suggestions

    if not body.outputs:
        return result

    # ---- step 7: runnable workflows, and the next dataset to add ----------------------------
    recommended = chains.recommend(k, body.challenge, list(body.outputs), context(body.objective), generated=3)
    for c in recommended["chains"]:
        c["readiness"] = readiness(c)
    recommended["chains"].sort(key=lambda c: ({"hand": 0, "area": 1, "none": 2}[c["readiness"]],
                                              c["kind"] != "reference", -(c["score"] or 0)))
    result["workflows"] = recommended
    result["next_datasets"] = next_datasets(k, recommended["chains"], discovered, hand, data_step, body.data)
    return result


def next_datasets(k, workflows: list[dict], discovered: list[dict], hand: set[str],
                  data_step: str | None = None, data: list | None = None, limit: int = 3) -> list[dict]:
    """The datasets of the area that would bring the workflows closest to "ready with your data".

    Two ways a dataset helps:
      * it provides variables the workflows need and you do not have;
      * it provides a forcing you have, at a FINER time step, for the workflows your data is
        too coarse for (daily rain cannot drive an hourly flood model).
    For each: the workflows it completes (nothing left to find) and those it helps. Adding it
    re-runs the whole flow.
    """
    needs = {c["id"]: {i["id"] for i in c["inputs"] if i["state"] != "have"} for c in workflows}
    too_coarse = [c for c in workflows if any("finer time step" in r for r in c["reasons"])]
    forcing_in_hand = {d.variable for d in (data or []) if d.step and roles_of(k, d.variable)[0] == "forcing"}
    ranked = []
    for dataset in discovered:
        if dataset["coverage"] != "full":
            continue
        offers = {v["id"] for v in dataset["variables"]} - hand
        useful = set().union(*(need & offers for need in needs.values())) if needs else set()
        finer = set()
        if data_step and too_coarse:
            for v in dataset["variables"]:
                if v["id"] in forcing_in_hand and any(
                        s["dataset"] == dataset["id"] and s["step"] in k.hours and k.hours[s["step"]] < k.hours[data_step]
                        for s in k.data.get(v["id"], [])):
                    finer.add(v["id"])
        if not useful and not finer:
            continue
        completes = [c for c in workflows if needs[c["id"]] and needs[c["id"]] <= offers and c not in too_coarse]
        helps = [c for c in workflows if (needs[c["id"]] & offers or (finer and c in too_coarse)) and c not in completes]
        ranked.append({
            "dataset": {k2: dataset[k2] for k2 in ("id", "label", "url", "publishers", "coverage", "start", "end",
                                                    "ongoing", "temporal_nature", "measured", "period")},
            "provides": [v for v in dataset["variables"] if v["id"] in useful],
            # forcing you have, but finer here: for the workflows your data is too coarse for
            "finer": [v for v in dataset["variables"] if v["id"] in finer],
            "completes": [c["label"] for c in completes],
            "helps": [c["label"] for c in helps],
            "score": len(completes) * 10 + len(helps) + len(useful | finer) / 100,
        })
    ranked.sort(key=lambda d: (-d["score"], d["dataset"]["label"] or ""))
    return ranked[:limit]


def declarable_variables(k) -> list[dict]:
    """The variables a user can declare: every one a method uses, with its roles and open data."""
    used: set[str] = set()
    for facts in k.facts.values():
        for prop in ("requiresMandatoryInput", "acceptsOptionalInput", "hasPhysicalParameter",
                     "isCalibratedAgainst", "requiresInitialCondition"):
            used |= set(facts.get(prop, []))
    found = []
    for variable in used:
        roles = roles_of(k, variable)
        found.append({**ref(k, variable), "role": roles[0], "roles": roles,
                      "datasets": len({s["dataset"] for s in k.data.get(variable, []) if s["dataset"]}),
                      "static": variable in k.static})
    found.sort(key=lambda v: (v["label"] or v["id"]).lower())
    return found
