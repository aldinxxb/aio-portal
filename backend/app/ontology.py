from app import queries
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
            {"id": dataset_id, "label": None, "publishers": [], "coverage": [], "url": None, "variables": []},
        )
        entry["label"] = entry["label"] or row.get("datasetLabel")
        entry["url"] = entry["url"] or row.get("page")
        # the same dataset appears once per variable / publisher / area: keep each once
        for key, iri, label in (
            ("publishers", "publisher", "publisherLabel"),
            ("coverage", "area", "areaLabel"),
            ("variables", "variable", "variableLabel"),
        ):
            if iri in row:
                item = {"id": local_name(row[iri]), "label": row.get(label)}
                if item["id"] not in [i["id"] for i in entry[key]]:
                    entry[key].append(item)
    return list(datasets.values())

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

def requirements_of(value_id: str) -> list[dict]:
    """The requirements implied by one problem-definition value (one dict per requirement)."""
    rows = run_select(queries.build("requirements_of_value", value=value_id))
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
    return facts


def state_variable_ids() -> set[str]:
    """Ids of all variables that describe a state (water level, soil moisture, ...)."""
    return {local_name(r["item"]) for r in run_select(queries.load("state_variables"))}


def output_variable_ids(output_id: str) -> set[str]:
    """Variables behind one expected output (Hydrograph -> {Discharge})."""
    rows = run_select(queries.build("output_variables", output=output_id))
    return {local_name(r["item"]) for r in rows}


def driver_variable_ids(driver_id: str) -> set[str]:
    """Variables that characterise one driver (Urbanization -> {ImperviousFraction, ...})."""
    rows = run_select(queries.build("driver_variables", driver=driver_id))
    return {local_name(r["item"]) for r in rows}