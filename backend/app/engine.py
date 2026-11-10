from collections import Counter
from types import SimpleNamespace

from app import ontology, rules
from app.config import WEIGHTS

DIRECT = "directly_applicable"
COMPLEMENT = "needs_complementary_data"
UNKNOWN = "inputs_not_recorded"

STATUS_ORDER = {DIRECT: 0, COMPLEMENT: 1, UNKNOWN: 2}


def evaluate(method: dict, selected_processes: set[str], available: set[str]) -> dict | None:
    """Judge one method for one user. Returns None if the method is not relevant."""
    modeled = [p for p in method["processes"] if p in selected_processes]
    if not modeled:
        return None  # it does not model any process the user cares about

    process_match = len(modeled) / len(selected_processes)

    labels = {i["id"]: i["label"] or i["id"] for i in method["inputs"]}
    needed = list(labels)
    have = [i for i in needed if i in available]
    missing = [i for i in needed if i not in available]

    if not needed:
        status, coverage, score = UNKNOWN, None, None
        explanation = "The ontology records no input variables for this method, so we cannot tell what data it needs."
    else:
        coverage = len(have) / len(needed)
        score = round(WEIGHTS["input_coverage"] * coverage + WEIGHTS["process_match"] * process_match, 3)
        status = DIRECT if not missing else COMPLEMENT
        if not missing:
            explanation = f"You have all {len(needed)} required input(s): {', '.join(labels[i] for i in have)}."
        else:
            explanation = (
                f"You have {len(have)} of {len(needed)} required input(s). "
                f"Missing: {', '.join(labels[i] for i in missing)}."
            )

    return {
        "id": method["id"],
        "label": method["label"],
        "status": status,
        "score": score,
        "input_coverage": coverage,
        "process_match": round(process_match, 3),
        "processes": modeled,
        "inputs_available": [{"id": i, "label": labels[i]} for i in have],
        "inputs_missing": [{"id": i, "label": labels[i]} for i in missing],
        "explanation": explanation,
    }


def sort_key(result: dict):
    return (STATUS_ORDER[result["status"]], -(result["score"] or 0), result["label"] or "")


def matches_filters(trait: dict | None, scales: set[str], time_steps: set[str]) -> bool:
    """Does a method satisfy the optional scale / time step filters?"""
    trait = trait or {"scales": set(), "time_steps": set()}
    if scales and not (scales & trait["scales"]):
        return False
    if time_steps and not (time_steps & trait["time_steps"]):
        return False
    return True


def check_method(profile: dict, available: set[str]) -> dict:
    """Compare the data a user has with the inputs of ONE method (see ontology.method_profile)."""
    mandatory = profile["mandatory_inputs"]
    optional = profile["optional_inputs"]

    have = [i for i in mandatory if i["id"] in available]
    missing = [i for i in mandatory if i["id"] not in available]

    if not mandatory:
        status, coverage = UNKNOWN, None
    else:
        status = DIRECT if not missing else COMPLEMENT
        coverage = round(len(have) / len(mandatory), 3)

    return {
        "status": status,
        "coverage": coverage,
        "inputs_available": have,
        "inputs_missing": missing,
        "optional_used": [i for i in optional if i["id"] in available],
        "optional_unused": [i for i in optional if i["id"] not in available],
    }


# ----------------------------------------------------------------------------
# Requirement rules (Lesson 37)
# ----------------------------------------------------------------------------

def has_problem(urr: dict) -> bool:
    """Did the user define a problem (goal, intent, scenario, drivers or outputs)?"""
    return any(
        [urr.get("objective"), urr.get("intent"), urr.get("scenario"),
         urr.get("drivers"), urr.get("outputs")]
    )


def problem_of(urr: dict) -> SimpleNamespace:
    """The validated URR dictionary as an object, with a default for every field."""
    return SimpleNamespace(
        challenge=urr["challenge"],
        objective=urr.get("objective"),
        intent=urr.get("intent"),
        scenario=urr.get("scenario"),
        entity=urr.get("entity"),
        drivers=list(urr.get("drivers", [])),
        outputs=list(urr.get("outputs", [])),
        available_variables=list(urr.get("available_variables", [])),
    )


def apply_verdicts(results: list[dict], verdicts: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """Combine ranked results with the rule verdicts (pure function: no database).

    - a method with a failed HARD rule leaves the list (and is reported, with why);
    - for the others the SOFT adjustment is added to the score (kept between 0 and 1),
      and the original score stays available as 'base_score';
    - every kept method gets its list of 'reasons'.
    """
    kept: list[dict] = []
    excluded: list[dict] = []
    for result in results:
        verdict = verdicts.get(result["id"])
        if verdict is None:
            kept.append(result)
            continue
        if verdict["excluded"]:
            why = [r for r in verdict["reasons"] if r["strength"] == "hard" and r["status"] == "fail"]
            excluded.append({"id": result["id"], "label": result["label"], "reasons": why})
            continue
        result["base_score"] = result["score"]
        result["rule_adjustment"] = verdict["adjustment"]
        if result["score"] is not None:
            result["score"] = round(min(1.0, max(0.0, result["score"] + verdict["adjustment"])), 3)
        result["reasons"] = verdict["reasons"]
        kept.append(result)
    return kept, excluded


def recommend(validated: dict, use_rules: bool | None = None) -> dict:
    """Take a validated URR (see urr.validate) and return ranked, explained methods.

    use_rules: None = apply the requirement rules only if the user defined a problem
    (goal, intent, scenario, drivers or outputs); True / False forces it.
    """
    urr = validated["urr"]
    selected = set(urr["processes"]["values"])
    available = set(urr["available_variables"])
    scales = set(urr.get("scales", []))
    time_steps = set(urr.get("time_steps", []))

    methods = ontology.list_methods(urr["challenge"])
    results = [r for m in methods if (r := evaluate(m, selected, available))]

    filtered_out = 0
    if scales or time_steps:
        traits = ontology.list_method_traits(urr["challenge"])
        kept = [r for r in results if matches_filters(traits.get(r["id"]), scales, time_steps)]
        filtered_out = len(results) - len(kept)
        results = kept

    if use_rules is None:
        use_rules = has_problem(urr)

    requirements_found: list[dict] = []
    excluded_methods: list[dict] = []
    if use_rules:
        judged = rules.judge_methods(problem_of(urr), methods)
        requirements_found = judged["requirements"]
        verdicts = {v["id"]: v for v in judged["methods"]}
        results, excluded_methods = apply_verdicts(results, verdicts)

    results.sort(key=sort_key)

    return {
        "urr": urr,
        "counts": dict(Counter(r["status"] for r in results)),
        "filtered_out": filtered_out,
        "rules_applied": use_rules,
        "requirements": requirements_found,
        "excluded_by_rules": len(excluded_methods),
        "excluded_methods": excluded_methods,
        "results": results,
    }


def reach(available: set[str]) -> list[dict]:
    """For every challenge: what the user's data already allows (Entry 3)."""
    reached = []
    for challenge in ontology.list_challenges():
        processes = [p["id"] for p in ontology.list_processes(challenge["id"])]
        validated = {
            "urr": {
                "challenge": challenge["id"],
                "processes": {"values": processes, "source": "derived"},
                "available_variables": sorted(available),
            }
        }
        recommendation = recommend(validated, use_rules=False)
        direct = [r for r in recommendation["results"] if r["status"] == DIRECT]
        reached.append(
            {
                "id": challenge["id"],
                "label": challenge["label"],
                "counts": recommendation["counts"],
                "best": [
                    {"id": r["id"], "label": r["label"], "score": r["score"]} for r in direct[:3]
                ],
            }
        )
    reached.sort(key=lambda c: (-c["counts"].get(DIRECT, 0), c["label"] or c["id"]))
    return reached


def find_datasets(variables: set[str], limit: int = 12) -> list[dict]:
    """Datasets providing at least one of the variables, best coverage first."""
    found = []
    for dataset in ontology.list_datasets():
        provides = [v for v in dataset["variables"] if v["id"] in variables]
        if provides:
            found.append(
                {
                    "id": dataset["id"],
                    "label": dataset["label"],
                    "publishers": dataset["publishers"],
                    "coverage": dataset["coverage"],
                    "url": dataset["url"],
                    "provides": provides,
                }
            )
    found.sort(key=lambda d: (-len(d["provides"]), d["label"] or d["id"]))
    return found[:limit]


def workflow(validated: dict, focus: list[str], top: int = 3) -> dict:
    """The path from challenge to data for the best methods, as graph nodes and edges."""
    urr = validated["urr"]
    results = recommend(validated)["results"]
    chosen = [r for r in results if r["id"] in focus] if focus else results
    chosen = chosen[:top]

    challenge_id = urr["challenge"]
    challenge_label = next(
        (c["label"] for c in ontology.list_challenges() if c["id"] == challenge_id), None
    )
    process_labels = {p["id"]: p["label"] for p in ontology.list_processes(challenge_id)}

    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def node(kind: str, item_id: str, label: str | None, have: bool | None = None) -> str:
        key = f"{kind}:{item_id}"
        nodes.setdefault(key, {"id": key, "kind": kind, "label": label or item_id, "have": have})
        return key

    def edge(source: str, target: str) -> None:
        link = {"source": source, "target": target}
        if link not in edges:
            edges.append(link)

    challenge_key = node("challenge", challenge_id, challenge_label)
    missing: set[str] = set()
    for r in chosen:
        method_key = node("method", r["id"], r["label"])
        for process_id in r["processes"]:
            process_key = node("process", process_id, process_labels.get(process_id))
            edge(challenge_key, process_key)
            edge(process_key, method_key)
        profile = ontology.method_profile(r["id"]) or {"software": []}
        for software in profile["software"][:3]:
            edge(method_key, node("software", software["id"], software["label"]))
        for item in r["inputs_available"]:
            edge(method_key, node("variable", item["id"], item["label"], have=True))
        for item in r["inputs_missing"]:
            edge(method_key, node("variable", item["id"], item["label"], have=False))
            missing.add(item["id"])

    for dataset in find_datasets(missing, limit=4):
        dataset_key = node("dataset", dataset["id"], dataset["label"])
        for variable in dataset["provides"]:
            edge(f"variable:{variable['id']}", dataset_key)

    return {"nodes": list(nodes.values()), "edges": edges}