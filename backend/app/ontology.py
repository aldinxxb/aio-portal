import re

from app import queries
from app.config import NAMESPACES
from app.sparql_client import run_select


def local_name(iri: str) -> str:
    """'https://w3id.org/aio#Flood' -> 'Flood'"""
    return iri.split("#")[-1]


def list_challenges() -> list[dict]:
    rows = run_select(queries.load("challenges"))
    return [{"id": local_name(r["challenge"]), "label": r.get("label")} for r in rows]


def list_processes(challenge_id: str) -> list[dict]:
    rows = run_select(queries.build("processes_of_challenge", challenge=challenge_id))
    return [{"id": local_name(r["process"]), "label": r.get("label")} for r in rows]


def list_variables() -> list[dict]:
    rows = run_select(queries.load("variables"))
    return [{"id": local_name(r["variable"]), "label": r.get("label")} for r in rows]


def list_methods(challenge_id: str) -> list[dict]:
    rows = run_select(queries.build("methods_for_challenge", challenge=challenge_id))

    methods: dict[str, dict] = {}
    for row in rows:
        method_id = local_name(row["method"])
        method = methods.setdefault(
            method_id,
            {"id": method_id, "label": row.get("methodLabel"), "processes": [], "inputs": []},
        )
        # the same method appears once per process and per input: keep each only once
        process_id = local_name(row["process"])
        if process_id not in method["processes"]:
            method["processes"].append(process_id)
        if "input" in row:
            input_id = local_name(row["input"])
            if input_id not in [i["id"] for i in method["inputs"]]:
                method["inputs"].append({"id": input_id, "label": row.get("inputLabel")})
    return list(methods.values())

def option_counts(query_name: str, **concepts: str) -> list[dict]:
    """Run an 'options' query. Its rows have ?item ?label ?count (how many methods)."""
    rows = run_select(queries.build(query_name, **concepts) if concepts else queries.load(query_name))
    return [
        {"id": local_name(r["item"]), "label": r.get("label"), "count": int(r["count"])}
        for r in rows
    ]
def list_method_traits(challenge_id: str) -> dict[str, dict]:
    """For each method of the challenge: which scales and time steps the ontology records."""
    rows = run_select(queries.build("method_traits", challenge=challenge_id))
    traits: dict[str, dict] = {}
    for row in rows:
        entry = traits.setdefault(
            local_name(row["method"]), {"scales": set(), "time_steps": set()}
        )
        if "scale" in row:
            entry["scales"].add(local_name(row["scale"]))
        if "timeStep" in row:
            entry["time_steps"].add(local_name(row["timeStep"]))
    return traits
# which list of the profile each kind of row belongs to
PROFILE_LISTS = {
    "process": "processes",
    "challenge": "challenges",
    "software": "software",
    "scale": "scales",
    "timestep": "time_steps",
    "mandatory": "mandatory_inputs",
    "optional": "optional_inputs",
    "output": "outputs",
}


def method_profile(method_id: str) -> dict | None:
    """Everything the ontology says about one method, or None if it does not exist."""
    rows = run_select(queries.build("method_profile", method=method_id))
    if not rows:
        return None

    profile: dict = {"id": method_id, "label": None}
    for key in PROFILE_LISTS.values():
        profile[key] = []

    for row in rows:
        item = {"id": local_name(row["item"]), "label": row.get("label")}
        if row["kind"] == "method":
            profile["label"] = item["label"]
        else:
            target = profile[PROFILE_LISTS[row["kind"]]]
            if item not in target:
                target.append(item)

    for key in PROFILE_LISTS.values():
        profile[key].sort(key=lambda x: x["label"] or x["id"])
    return profile
def list_datasets() -> list[dict]:
    """Every catalogued dataset with the variables it provides."""
    rows = run_select(queries.load("datasets"))
    datasets: dict[str, dict] = {}
    for row in rows:
        dataset_id = local_name(row["dataset"])
        entry = datasets.setdefault(
            dataset_id,
            {
                "id": dataset_id, "label": None, "publishers": [], "coverage": [], "url": None,
                "variables": [],
                # temporal facts of the dataset
                "start": None, "end": None, "ongoing": None, "temporal_nature": None,
            },
        )
        entry["label"] = entry["label"] or row.get("datasetLabel")
        entry["url"] = entry["url"] or row.get("page")
        entry["start"] = entry["start"] or row.get("start")
        entry["end"] = entry["end"] or row.get("end")
        entry["temporal_nature"] = entry["temporal_nature"] or row.get("natureLabel")
        if "ongoing" in row:
            entry["ongoing"] = row["ongoing"] == "true"
        # the same dataset appears once per variable / publisher / area: keep each once
        for key, iri, label in (
            ("publishers", "publisher", "publisherLabel"),
            ("coverage", "area", "areaLabel"),
            ("variables", "variable", "variableLabel"),
        ):
            if iri in row:
                item = {"id": local_name(row[iri]), "label": row.get(label)}
                if item["id"] not in [i["id"] for i in entry[key]]:
                    if key == "variables":
                        item["time_steps"] = []     # e.g. ["1 hour"]
                        item["grids"] = []          # e.g. ["0.25°"] or ["1 km"]
                    entry[key].append(item)
        # resolution of this row's variable (one variable can come at several resolutions)
        variable = next(v for v in entry["variables"] if v["id"] == local_name(row["variable"]))
        for target, text in (
            (variable["time_steps"], readable_duration(row.get("timeStep"))),
            (variable["grids"], readable_grid(row.get("gridMeters"), row.get("gridDegrees"))),
        ):
            if text and text not in target:
                target.append(text)
    return list(datasets.values())


DURATION = re.compile(r"^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?$")
DURATION_UNITS = ("year", "month", "day", "hour", "minute")


def readable_duration(value: str | None) -> str | None:
    """'PT1H' -> '1 hour', 'P10D' -> '10 days'. Unknown shapes are returned as they are."""
    if not value:
        return None
    match = DURATION.match(value)
    if not match:
        return value
    parts = [
        f"{int(n)} {unit}{'' if int(n) == 1 else 's'}"
        for n, unit in zip(match.groups(), DURATION_UNITS) if n
    ]
    return " ".join(parts) or value


def readable_grid(meters: str | None, degrees: str | None) -> str | None:
    """Grid size as text: '250 m', '8 km' or '0.25°'."""
    if meters:
        size = float(meters)
        return f"{size / 1000:g} km" if size >= 1000 else f"{size:g} m"
    if degrees:
        return f"{float(degrees):g}°"
    return None

# The question types of the new wizard steps, and the ontology class behind each.
# Only names listed here can ever reach a query.
VOCABULARIES = {
    "objective": "StudyObjective",   # Forecasting, Estimation, ...
    "intent": "DecisionIntent",      # Prediction, Comparison, ...
    "scenario": "Scenario",          # Historical, Current, Future, What-if
    "entity": "WaterEntity",         # River, Aquifer, UrbanArea, ...
    "driver": "Factor",              # Rainfall, Urbanization, ...
    "output": "ExpectedOutput",      # Hydrograph, FloodExtentMap, ...
}


def list_vocabulary(kind: str) -> list[dict]:
    """All values of one kind, e.g. kind='objective' -> the 6 study objectives."""
    if kind not in VOCABULARIES:
        raise ValueError(f"Unknown vocabulary: {kind!r}")
    rows = run_select(queries.build("vocabulary", kind=VOCABULARIES[kind]))
    return [{"id": local_name(r["item"]), "label": r.get("label")} for r in rows]


def list_outputs(challenge_id: str) -> list[dict]:
    """Outputs usually expected for a challenge, the primary ones first."""
    rows = run_select(queries.build("outputs_for_challenge", challenge=challenge_id))
    outputs: dict[str, dict] = {}
    for row in rows:
        output_id = local_name(row["item"])
        output = outputs.setdefault(
            output_id,
            {
                "id": output_id,
                "label": row.get("label"),
                "question": row.get("question"),
                "primary": row.get("isPrimary") == "1",
                "entities": [],
            },
        )
        if "entity" in row:
            entity_id = local_name(row["entity"])
            if entity_id not in output["entities"]:
                output["entities"].append(entity_id)
    # primary first, then alphabetical (None labels sort last)
    return sorted(outputs.values(), key=lambda o: (not o["primary"], o["label"] or "~"))


def list_drivers(challenge_id: str) -> list[dict]:
    """Key drivers of a challenge; 'default' marks the one assumed if the user skips."""
    rows = run_select(queries.build("drivers_for_challenge", challenge=challenge_id))
    return [
        {
            "id": local_name(r["item"]),
            "label": r.get("label"),
            "default": r.get("isDefault") == "1",
        }
        for r in rows
    ]

_requirements: dict[str, list[dict]] = {}       # {value: its requirements}, read once


def forget_requirements() -> None:
    _requirements.clear()


def requirements_of(value_id: str) -> list[dict]:
    """The requirements implied by one problem-definition value (one dict per requirement).

    Every value's requirements are read in ONE query the first time (the wizard asks for
    dozens of values per step), then served from memory until the ontology is refreshed.
    """
    if not _requirements:
        rows = run_select(queries.load("requirements_all"))
        by_value: dict[str, list[dict]] = {}
        for row in rows:
            by_value.setdefault(local_name(row["value"]), []).append(row)
        _requirements.update({value: _group_requirements(found) for value, found in by_value.items()})
        _requirements.setdefault("", [])          # marks the table as read, even if empty
    return [dict(r, allowed_values=list(r["allowed_values"]), applies_to=list(r["applies_to"]))
            for r in _requirements.get(value_id, [])]


def _group_requirements(rows: list[dict]) -> list[dict]:
    """Rows of the requirements query -> one dict per requirement."""
    found: dict[str, dict] = {}
    for row in rows:
        req_id = local_name(row["req"])
        req = found.setdefault(
            req_id,
            {
                "id": req_id,
                "kind": local_name(row["type"]).replace("Requirement", "").lower(),
                "label": row.get("label"),
                "rationale": row.get("rationale"),
                "strength": local_name(row["strength"]).lower() if "strength" in row else "none",
                "weight": float(row["weight"]) if "weight" in row else 0.0,
                "rule_id": row.get("ruleId"),
                "on_property": local_name(row["onProperty"]) if "onProperty" in row else None,
                "allowed_values": [],
                "allowed_literal": row.get("allowedLiteral"),
                "applies_to": [],
            },
        )
        if "allowedValue" in row:
            value = local_name(row["allowedValue"])
            if value not in req["allowed_values"]:
                req["allowed_values"].append(value)
        if "appliesTo" in row:
            kind = local_name(row["appliesTo"])
            if kind not in req["applies_to"]:
                req["applies_to"].append(kind)
    return list(found.values())
def method_facts() -> dict[str, dict[str, list[str]]]:
    """For every method: {property name: [values]}, e.g. facts['SCS-CN']['hasTemporalMode']."""
    rows = run_select(queries.load("method_facts"))
    facts: dict[str, dict[str, list[str]]] = {}
    for row in rows:
        method = facts.setdefault(local_name(row["method"]), {})
        values = method.setdefault(local_name(row["prop"]), [])
        value = local_name(row["value"])
        if value not in values:
            values.append(value)
    # values in a stable order: GraphDB returns them in its storage order, which changes when
    # the data is reloaded (a method's roles, its software...). Sorted, the answers stay the same.
    for method in facts.values():
        for values in method.values():
            values.sort()
    return facts


def state_variable_ids() -> set[str]:
    """Ids of all variables that describe a state (water level, soil moisture, ...)."""
    return {local_name(r["item"]) for r in run_select(queries.load("state_variables"))}


def output_variables(output_id: str) -> list[dict]:
    """Variables behind one expected output, with labels (Hydrograph -> discharge)."""
    rows = run_select(queries.build("output_variables", output=output_id))
    found: dict[str, dict] = {}
    for row in rows:
        variable_id = local_name(row["item"])
        found.setdefault(variable_id, {"id": variable_id, "label": row.get("label")})
    return list(found.values())


def output_variable_ids(output_id: str) -> set[str]:
    """Variables behind one expected output (Hydrograph -> {Discharge})."""
    return {v["id"] for v in output_variables(output_id)}


# which list of the details each kind of row belongs to
DETAIL_LISTS = {
    "physical": "physical_parameters",
    "calibration": "calibration_parameters",
    "output": "outputs",
    "software": "software",
}


def empty_details() -> dict:
    return {key: [] for key in DETAIL_LISTS.values()}


def list_method_details(challenge_id: str) -> dict[str, dict]:
    """For each method of the challenge: its parameters, its outputs and its software."""
    rows = run_select(queries.build("method_details", challenge=challenge_id))
    details: dict[str, dict] = {}
    for row in rows:
        entry = details.setdefault(local_name(row["method"]), empty_details())
        target = entry[DETAIL_LISTS[row["kind"]]]
        item_id = local_name(row["item"])
        if item_id not in [i["id"] for i in target]:
            target.append({"id": item_id, "label": row.get("label")})
    for entry in details.values():
        for target in entry.values():
            target.sort(key=lambda x: (x["label"] or x["id"]).lower())
    return details


def driver_variable_ids(driver_id: str) -> set[str]:
    """Variables that characterise one driver (Urbanization -> {ImperviousFraction, ...})."""
    rows = run_select(queries.build("driver_variables", driver=driver_id))
    return {local_name(r["item"]) for r in rows}

# ----------------------------------------------------------------------------
# Ontology 0.8.0: generic readers used by the chain layer (knowledge.py)
# ----------------------------------------------------------------------------

def value_of(text: str) -> str:
    """An ontology IRI becomes its short name; any other value stays as it is."""
    return local_name(text) if text.startswith(tuple(NAMESPACES)) else text


def describe(kind: str) -> dict[str, dict[str, list[str]]]:
    """Every individual of one class: {id: {property: [values]}}."""
    rows = run_select(queries.build("describe", kind=kind))
    found: dict[str, dict[str, list[str]]] = {}
    for row in rows:
        values = found.setdefault(local_name(row["s"]), {}).setdefault(
            row["p"].split("#")[-1].split("/")[-1], []
        )
        value = value_of(row["o"])
        if value not in values:
            values.append(value)
    for item in found.values():                    # stable order, whatever the storage order
        for values in item.values():
            values.sort()
    return found


def pairs(prop: str) -> dict[str, set[str]]:
    """One property as {subject: {values}}, e.g. pairs('isExpressedBy')['Hydrograph']."""
    found: dict[str, set[str]] = {}
    for row in run_select(queries.build("pairs", prop=prop)):
        found.setdefault(local_name(row["s"]), set()).add(value_of(row["o"]))
    return found


def all_labels() -> dict[str, str]:
    """Label of everything: {id: label}. English when it exists, another language otherwise."""
    labels: dict[str, str] = {}
    english: set[str] = set()
    for row in run_select(queries.load("labels")):
        item = local_name(row["s"])
        is_english = row.get("lang", "") in ("en", "")
        if item not in labels or (is_english and item not in english):
            labels[item] = row["label"]
        if is_english:
            english.add(item)
    return labels


def data_by_variable() -> dict[str, list[dict]]:
    """Open data per variable: {variable: [{dataset, provenance, step}]}."""
    found: dict[str, list[dict]] = {}
    for row in run_select(queries.load("data_variables")):
        source = {
            "dataset": local_name(row["dataset"]) if "dataset" in row else None,
            "provenance": local_name(row["provenance"]) if "provenance" in row else None,
            "step": local_name(row["step"]) if "step" in row else None,
        }
        sources = found.setdefault(local_name(row["variable"]), [])
        if source not in sources:
            sources.append(source)
    return found


def variable_kinds() -> dict[str, set[str]]:
    """Nature of each variable: {'Discharge': {'FluxVariable'}, 'DTM': {'ParameterVariable'}}."""
    found: dict[str, set[str]] = {}
    for row in run_select(queries.load("variable_kinds")):
        found.setdefault(local_name(row["variable"]), set()).add(local_name(row["kind"]))
    return found


def replacements() -> dict[str, str]:
    """Deprecated names and what replaces them: {'Catchement': 'Catchment', ...}."""
    return {local_name(r["old"]): local_name(r["new"]) for r in run_select(queries.load("replaced"))}


def plain_questions() -> dict[str, str]:
    """The question each expected output answers: {'PeakFlow': 'How big is the flood peak?'}."""
    return {local_name(r["s"]): r["question"] for r in run_select(queries.load("plain_questions"))}
