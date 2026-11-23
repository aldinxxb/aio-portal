from collections import Counter
from types import SimpleNamespace

from app import chains, knowledge, ontology, requirements, rules, timesteps
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


def matches_filters(trait: dict | None, scales: set[str], time_steps: set[str],
                    supports: list[str] | None = None, hours: dict | None = None) -> bool:
    """Does a method satisfy the optional scale / time step filters?

    Time step (rule B): the method must run as finely as, or FINER than, a step the user
    wants. A finer method always qualifies, because its results can be aggregated.
    """
    trait = trait or {"scales": set(), "time_steps": set()}
    if scales and not (scales & trait["scales"]):
        return False
    if time_steps:
        if hours is None:      # no ontology order given: plain comparison of names
            return bool(time_steps & trait["time_steps"])
        return any(timesteps.can_deliver(hours, supports or [], step) for step in time_steps)
    return True


def describe_time_steps(k, method_id: str, wanted: set[str], data_step: str | None) -> dict:
    """What to tell the user about the time step of one method."""
    supports = chains.get(k, method_id, "supportsTimeStep")
    typical = chains.get(k, method_id, "hasTypicalTimeStep")

    def name(step: str) -> str:
        return k.labels.get(step, step)

    notes: list[str] = []
    # rule B: finer than what the user wants -> the results are aggregated
    if wanted and supports and not (wanted & set(supports)):
        finest = timesteps.order(k.hours, supports)[0]
        notes.append(
            f"Runs at a finer step ({name(finest)}): its results are aggregated to "
            + " / ".join(name(s) for s in timesteps.order(k.hours, wanted)) + "."
        )
    # rule A: the data of the user is coarser than every step the method runs at
    usable = True
    if data_step:
        usable = timesteps.usable_as_is(k.hours, supports, data_step)
        if not usable:
            notes.append(timesteps.DISAGGREGATION_WARNING)
        elif supports and data_step not in supports:
            notes.append(f"Your {name(data_step)} data is finer than this method needs: it is aggregated.")
    return {
        "supports": [chains.ref(k, s) for s in timesteps.order(k.hours, supports)],
        "typical": [chains.ref(k, s) for s in timesteps.order(k.hours, typical)],
        "needs_disaggregation": not usable,
        "notes": notes,
    }


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


def two_views(k, result: dict, available: set[str]) -> dict:
    """The two questions a result answers, kept apart:

      compatibility  does the METHOD suit the study? (processes, requirement rules,
                     the jobs it can do in a model) - nothing to do with the data;
      availability   can its DATA be gathered? (what you have, what open data provides,
                     what has no source), each input with its kind: forcing, boundary
                     condition, static description or initial state.
    """
    method = result["id"]
    reasons = result.get("reasons", [])
    failed = [r for r in reasons if r["status"] == "fail"]
    passed = [r for r in reasons if r["status"] == "pass"]
    fit = result["process_match"] + (result.get("rule_adjustment") or 0.0)

    def source(variable: str) -> str:
        if variable in available:
            return "have"
        return "open_data" if variable in k.obtainable else "missing"

    initial = set(chains.get(k, method, "requiresInitialCondition"))
    inputs = [
        {**chains.ref(k, v), "kind": chains.input_kind(k, v, method), "state": source(v), "required": True}
        for v in sorted(set(chains.get(k, method, "requiresMandatoryInput")) - initial)
    ] + [
        {**chains.ref(k, v), "kind": chains.STATIC, "state": source(v), "required": False}
        for v in sorted(chains.get(k, method, "hasPhysicalParameter"))
    ] + [
        {**chains.ref(k, v), "kind": chains.INITIAL, "state": "initial", "required": False}
        for v in sorted(initial)
    ]
    needed = [i for i in inputs if i["required"]]
    have = sum(1 for i in needed if i["state"] == "have")
    reachable = sum(1 for i in needed if i["state"] in ("have", "open_data"))

    return {
        "roles": chains.role_views(k, method),
        "inputs": inputs,
        "compatibility": {
            "score": round(min(1.0, max(0.0, fit)), 3),
            "process_match": result["process_match"],
            "rules_passed": len(passed),
            "rules_failed": len(failed),
        },
        "availability": {
            # share of the required inputs you already have / could have with open data
            "score": round(have / len(needed), 3) if needed else None,
            "with_open_data": round(reachable / len(needed), 3) if needed else None,
            "have": have,
            "open_data": reachable - have,
            "missing": len(needed) - reachable,
            "needs_disaggregation": result["time_step"]["needs_disaggregation"],
        },
    }


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

    k = knowledge.load()
    filtered_out = 0
    if scales or time_steps:
        traits = ontology.list_method_traits(urr["challenge"])
        kept = [
            r for r in results
            if matches_filters(traits.get(r["id"]), scales, time_steps,
                               chains.get(k, r["id"], "supportsTimeStep"), k.hours)
        ]
        filtered_out = len(results) - len(kept)
        results = kept

    # time step of each method: finer than asked (aggregate) or too fine for the data
    data_step = urr.get("data_time_step")
    for result in results:
        result["time_step"] = describe_time_steps(k, result["id"], time_steps, data_step)

    if use_rules is None:
        use_rules = has_problem(urr)

    requirements_found: list[dict] = []
    excluded_methods: list[dict] = []
    if use_rules:
        judged = rules.judge_methods(problem_of(urr), methods)
        requirements_found = judged["requirements"]
        verdicts = {v["id"]: v for v in judged["methods"]}
        results, excluded_methods = apply_verdicts(results, verdicts)

    # methods that would need the data to be split into finer steps come last
    results.sort(key=lambda r: (r["time_step"]["needs_disaggregation"], sort_key(r)))

    # what to show on each method: parameters, outputs produced, software
    details = ontology.list_method_details(urr["challenge"])
    for result in results:
        result.update(details.get(result["id"]) or ontology.empty_details())
        result.update(two_views(k, result, available))

    # the outputs the user expects, each with the variables behind it
    # outputs of the challenge: question, form, variables, water entities they concern
    typical = {o["id"]: o for o in ontology.list_outputs(urr["challenge"])}
    labels = {o["id"]: o["label"] for o in ontology.list_vocabulary("output")} if urr.get("outputs") else {}
    expected_outputs = []
    for o in urr.get("outputs", []):
        variables = []
        for v in ontology.output_variables(o):
            makers = [r for r in results if v["id"] in {x["id"] for x in r["outputs"]}]
            variables.append({
                **v,
                # the recommended methods that compute it (best first)
                "computed_by": [{"id": r["id"], "label": r["label"]} for r in makers[:4]],
                "count": len(makers),
                "derivable_from": chains.refs(k, next(
                    (w["inputs"] for w in k.derivations.get(v["id"], []) if w["model"]), set())),
            })
        expected_outputs.append({
            "id": o, "label": labels.get(o), "variables": variables,
            "question": k.questions.get(o),
            "forms": [chains.ref(k, f) for f in sorted(k.output_forms.get(o, set()))],
            "entities": chains.refs(k, typical.get(o, {}).get("entities", [])),
        })

    # water entities concerned by the problem (for information): those of the chosen outputs,
    # else those of the main outputs of the challenge
    concern = urr.get("outputs") or [o["id"] for o in typical.values() if o["primary"]]
    entities: dict[str, dict] = {}
    for o in concern:
        for e in typical.get(o, {}).get("entities", []):
            entities.setdefault(e, {**chains.ref(k, e), "outputs": []})["outputs"].append(
                labels.get(o) or k.labels.get(o) or o)
    related_entities = sorted(entities.values(), key=lambda e: (-len(e["outputs"]), e["label"] or e["id"]))

    return {
        "urr": urr,
        "expected_outputs": expected_outputs,
        "related_entities": related_entities,
        "related_processes": {
            "values": chains.refs(k, urr["processes"]["values"]),
            "source": urr["processes"]["source"],
            "primary": sorted(k.primary.get(urr["challenge"], set()) & set(urr["processes"]["values"])),
        },
        "counts": dict(Counter(r["status"] for r in results)),
        "filtered_out": filtered_out,
        "rules_applied": use_rules,
        "requirements": requirements_found,
        "excluded_by_rules": len(excluded_methods),
        "excluded_methods": excluded_methods,
        "results": results,
    }


def chains_for(validated: dict, licence: str | None = None, software: str | None = None) -> dict:
    """Recommended workflows (chains of methods) for a validated URR."""
    urr = validated["urr"]
    k = knowledge.load()
    modes = []
    if has_problem(urr):
        # hard requirements on the temporal mode (forecasting -> continuous) also bind chains
        for req in requirements.collect(problem_of(urr)):
            if (req["kind"] == "method" and req["strength"] == "hard"
                    and req["on_property"] == "hasTemporalMode"):
                modes.append(set(req["allowed_values"]))
    ctx = chains.context(
        available=urr["available_variables"],
        data_step=urr.get("data_time_step"),
        output_steps=urr.get("time_steps", []),
        licence=licence,
        modes=modes,
        software=software,
    )
    return chains.recommend(k, urr["challenge"], list(urr.get("outputs", [])), ctx)


def reach_details(k, challenge_id: str, results: list[dict], available: set[str]) -> dict:
    """More about one challenge for the Data entry: what is close, what to add, which workflows."""
    # methods one input away from being usable
    nearly = [
        {"id": r["id"], "label": r["label"], "missing": r["inputs_missing"][0]}
        for r in results if r["status"] == COMPLEMENT and len(r["inputs_missing"]) == 1
    ]
    # the data to add next: the variables that would make the most methods usable
    unlocks = Counter(n["missing"]["id"] for n in nearly)
    next_data = [
        {**chains.ref(k, variable), "unlocks": count, "open_data": variable in k.obtainable}
        for variable, count in unlocks.most_common(4)
    ]
    # the standard workflows of the challenge, judged with the data of the user
    found = chains.recommend(k, challenge_id, [], chains.context(available=available), generated=0)
    workflows = [
        {
            "id": c["id"], "label": c["label"], "status": c["status"], "reasons": c["reasons"],
            "software": c["software"],
            "methods": [s["method"] for s in c["steps"]],
            "inputs": c["inputs"],
        }
        for c in found["chains"]
    ]
    return {"nearly": nearly, "next_data": next_data, "workflows": workflows}


def reach(available: set[str]) -> list[dict]:
    """For every challenge: what the user's data already allows (Entry 3)."""
    reached = []
    k = knowledge.load()
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
                "direct": [
                    {"id": r["id"], "label": r["label"], "score": r["score"],
                     "outputs": r["outputs"], "software": r["software"]} for r in direct
                ],
                **reach_details(k, challenge["id"], recommendation["results"], available),
            }
        )
    reached.sort(key=lambda c: (-c["counts"].get(DIRECT, 0), c["label"] or c["id"]))
    return reached


def dataset_card(dataset: dict, provides: list[dict]) -> dict:
    """One dataset as the open data layer shows it: who, where, when, and what it provides."""
    return {
        "id": dataset["id"],
        "label": dataset["label"],
        "publishers": dataset["publishers"],
        "coverage": dataset["coverage"],            # spatial: the areas covered
        "url": dataset["url"],
        "start": dataset["start"],                  # temporal: period covered
        "end": dataset["end"],
        "ongoing": dataset["ongoing"],              # still updated?
        "temporal_nature": dataset["temporal_nature"],
        "provides": provides,                       # each with its time steps and grid sizes
    }


def find_datasets(variables: set[str], limit: int = 12) -> list[dict]:
    """Datasets providing at least one of the variables, best coverage first."""
    found = []
    for dataset in ontology.list_datasets():
        provides = [v for v in dataset["variables"] if v["id"] in variables]
        if provides:
            found.append(dataset_card(dataset, provides))
    found.sort(key=lambda d: (-len(d["provides"]), d["label"] or d["id"]))
    return found[:limit]


def matches(variable: dict, words: list[str]) -> bool:
    """Does every word of the search appear in the variable's name or id?"""
    name = f"{variable['label'] or ''} {variable['id']}".lower()
    return all(word in name for word in words)


def matches_dataset(dataset: dict, words: list[str]) -> bool:
    """Does every word of the search appear in the dataset's name, id or publisher?"""
    name = " ".join(
        [dataset["label"] or "", dataset["id"]] + [p["label"] or p["id"] for p in dataset["publishers"]]
    ).lower()
    return all(word in name for word in words)


def search_datasets(text: str) -> dict:
    """Search the catalogue by variable name OR by dataset name (no limit).

    A dataset found by its own name (or publisher) lists ALL the variables it contains;
    a dataset found through a variable lists the matching variables only.
    """
    words = text.lower().split()
    found = []
    variables: dict[str, dict] = {}
    if words:
        for dataset in ontology.list_datasets():
            if matches_dataset(dataset, words):
                everything = sorted(dataset["variables"], key=lambda v: (v["label"] or v["id"]).lower())
                found.append({**dataset_card(dataset, everything), "matched_by": "dataset"})
                continue
            provides = [v for v in dataset["variables"] if matches(v, words)]
            if provides:
                found.append({**dataset_card(dataset, provides), "matched_by": "variable"})
                for v in provides:
                    variables.setdefault(v["id"], {"id": v["id"], "label": v["label"]})
    # datasets found by name first, then the ones providing the most matching variables
    found.sort(key=lambda d: (d["matched_by"] != "dataset",
                              -len(d["provides"]) if d["matched_by"] == "variable" else 0,
                              d["label"] or d["id"]))
    return {
        "query": text,
        "variables": sorted(variables.values(), key=lambda v: v["label"] or v["id"]),
        "datasets": found,
        "derived": derived_variables(words),
    }


def derived_variables(words: list[str] | None = None) -> list[dict]:
    """Variables that can be derived from other data, with how (all of them, or those matching)."""
    k = knowledge.load()
    found = []
    for variable in k.derivations:
        entry = {"id": variable, "label": k.labels.get(variable)}
        if words is None or (words and matches(entry, words)):
            sources = {s["dataset"] for s in k.data.get(variable, []) if s["dataset"]}
            found.append({**entry, "datasets": len(sources), "derivations": chains.derivations(k, variable)})
    return sorted(found, key=lambda v: (v["label"] or v["id"]).lower())


def dataset_suggestions() -> dict:
    """What can be typed in the search box: variable names and dataset names."""
    datasets = [
        {"id": d["id"], "label": d["label"], "count": len(d["variables"])}
        for d in ontology.list_datasets()
    ]
    datasets.sort(key=lambda d: (d["label"] or d["id"]).lower())
    derived = [{"id": v["id"], "label": v["label"]} for v in derived_variables()]
    return {"variables": dataset_variables(), "datasets": datasets, "derived": derived}


def dataset_variables() -> list[dict]:
    """Every variable some dataset provides, with the number of datasets (search suggestions)."""
    counts: Counter = Counter()
    labels: dict[str, str | None] = {}
    for dataset in ontology.list_datasets():
        for v in dataset["variables"]:
            counts[v["id"]] += 1
            labels[v["id"]] = v["label"]
    return sorted(
        ({"id": i, "label": labels[i], "count": n} for i, n in counts.items()),
        key=lambda v: (v["label"] or v["id"]).lower(),
    )


def pick_software(software: list[dict], shared: Counter, limit: int = 3) -> list[dict]:
    """The software to show for one method (pure function: no database).

    Software that runs several of the chosen methods comes first and is always kept,
    so the workflow can be grouped by software; the rest is cut at 'limit'.
    """
    ranked = sorted(software, key=lambda s: (-shared[s["id"]], (s["label"] or s["id"]).lower()))
    return [s for i, s in enumerate(ranked) if i < limit or shared[s["id"]] > 1]


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
    # how many of the chosen methods each software implements
    shared = Counter(s["id"] for r in chosen for s in r["software"])
    for r in chosen:
        method_key = node("method", r["id"], r["label"])
        for process_id in r["processes"]:
            process_key = node("process", process_id, process_labels.get(process_id))
            edge(challenge_key, process_key)
            edge(process_key, method_key)
        for software in pick_software(r["software"], shared):
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