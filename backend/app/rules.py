"""Applies the requirements of a URR to methods.

Two kinds of rule exist in the ontology:
  * value rules   -> "this property of the method must take one of these values"
                     (onProperty + allowedValue). One generic function handles them all.
  * pattern rules -> identified by a ruleId. Each ruleId has ONE small function below.
                     A ruleId without a function is reported as 'unknown', never a crash.

Every check answers with a status:
    "pass"     the method satisfies the rule
    "fail"     the method does not
    "unknown"  the ontology holds no information to decide

What a status does:
    hard rule + fail      -> the method is excluded
    soft rule + pass      -> score + weight
    soft rule + fail      -> score - weight / 2      (the ontology's own definition)
    anything + unknown    -> nothing happens

Layering: rules.py -> ontology.py, requirements.py, config.py.
"""
from app import config, ontology, requirements


# ----------------------------------------------------------------------------
# Context: the facts about the URR that rules need (computed once per request)
# ----------------------------------------------------------------------------

def build_context(urr, all_facts: dict) -> dict:
    wanted: set[str] = set()
    for output in urr.outputs:
        wanted |= ontology.output_variable_ids(output)

    # one-step chains: a method that feeds (mandatory input) a method producing the output
    feeder_vars: set[str] = set()
    for facts in all_facts.values():
        if wanted & set(facts.get("producesOutput", [])):
            feeder_vars |= set(facts.get("requiresMandatoryInput", []))

    driver_variables = {d: ontology.driver_variable_ids(d) for d in requirements.effective_drivers(urr)}

    return {
        "wanted_variables": wanted,
        "feeder_variables": feeder_vars,
        "driver_variables": driver_variables,
        "state_variables": ontology.state_variable_ids(),
        "available_variables": set(urr.available_variables),
    }


# ----------------------------------------------------------------------------
# Pattern rules: one function per ruleId. Each returns (status, detail).
# ----------------------------------------------------------------------------

def rule_produces_expected_output(facts, ctx):
    wanted = ctx["wanted_variables"]
    if not wanted:
        return "unknown", "no output with a known variable was chosen"
    produced = set(facts.get("producesOutput", []))
    direct = sorted(produced & wanted)
    if direct:
        return "pass", "computes " + ", ".join(direct)
    if produced & ctx["feeder_variables"]:
        return "pass", "feeds a method that computes " + ", ".join(sorted(wanted))
    return "fail", "does not compute " + ", ".join(sorted(wanted))


def rule_produces_state_variable(facts, ctx):
    states = sorted(set(facts.get("producesOutput", [])) & ctx["state_variables"])
    if states:
        return "pass", "computes the state " + ", ".join(states)
    return "fail", "computes no state variable (water level, soil moisture, ...)"


def rule_spatially_distributed_output(facts, ctx):
    distributed = "FullyDistributed" in facts.get("hasSpatialRepresentation", [])
    multi_d = set(facts.get("hasDimensionality", [])) & {"Dim2D", "Dim3D"}
    if distributed or multi_d:
        return "pass", "fully distributed or 2D/3D"
    return "fail", "neither fully distributed nor 2D/3D"


def rule_driver_variable_is_input(facts, ctx):
    if not ctx["driver_variables"]:
        return "unknown", "no driver to check"
    usable = set(facts.get("requiresInput", [])) | set(facts.get("hasPhysicalParameter", []))
    matched = [d for d, variables in ctx["driver_variables"].items() if variables & usable]
    if matched:
        return "pass", "can represent the driver " + ", ".join(sorted(matched))
    return "fail", "no variable of the chosen driver(s) is an input or physical parameter"


def rule_few_calibration_parameters(facts, ctx):
    n = len(facts.get("hasCalibrationParameter", []))
    if n <= config.FEW_CALIBRATION_PARAMETERS:
        return "pass", f"{n} calibration parameter(s)"
    return "fail", f"{n} calibration parameters"


def rule_physical_parameters_dominant(facts, ctx):
    physical = len(facts.get("hasPhysicalParameter", []))
    calibrated = len(facts.get("hasCalibrationParameter", []))
    if physical > calibrated:
        return "pass", f"{physical} physical vs {calibrated} calibration parameters"
    return "fail", f"{physical} physical vs {calibrated} calibration parameters"


def rule_calibration_data_available(facts, ctx):
    targets = set(facts.get("isCalibratedAgainst", []))
    if not targets:
        return "unknown", "the ontology records no calibration variable for this method"
    have = sorted(targets & ctx["available_variables"])
    if have:
        return "pass", "you have " + ", ".join(have) + " to calibrate it"
    return "fail", "needs " + ", ".join(sorted(targets)) + " to calibrate; none declared"


PATTERN_RULES = {
    "produces-expected-output": rule_produces_expected_output,
    "produces-state-variable": rule_produces_state_variable,
    "spatially-distributed-output": rule_spatially_distributed_output,
    "driver-variable-is-input": rule_driver_variable_is_input,
    "few-calibration-parameters": rule_few_calibration_parameters,
    "physical-parameters-dominant": rule_physical_parameters_dominant,
    "calibration-data-available": rule_calibration_data_available,
}


# ----------------------------------------------------------------------------
# Value rules: one generic function
# ----------------------------------------------------------------------------

def check_value_rule(requirement, facts):
    prop = requirement["on_property"]
    allowed = set(requirement["allowed_values"])
    have = facts.get(prop, [])
    if not have:
        return "unknown", f"{prop} is not recorded for this method"
    if set(have) & allowed:
        return "pass", f"{prop}: " + ", ".join(have)
    return "fail", f"{prop}: " + ", ".join(have) + " (needs " + " or ".join(sorted(allowed)) + ")"


# ----------------------------------------------------------------------------
# Judging one method
# ----------------------------------------------------------------------------

def check(requirement, facts, ctx):
    """Status and detail of one requirement for one method."""
    if requirement["rule_id"]:
        rule = PATTERN_RULES.get(requirement["rule_id"])
        if rule is None:
            return "unknown", f"rule '{requirement['rule_id']}' is not implemented yet"
        return rule(facts, ctx)
    if requirement["on_property"]:
        return check_value_rule(requirement, facts)
    return "unknown", "the requirement has neither a rule id nor a property"


def effect(requirement, status) -> float:
    """How much a result moves the score (hard rules never move it: they filter)."""
    if requirement["strength"] != "soft" or status == "unknown":
        return 0.0
    weight = requirement["weight"]
    return weight if status == "pass" else -weight / 2


def judge(facts: dict, method_requirements: list[dict], ctx: dict) -> dict:
    """Apply all method requirements to ONE method (facts = {property: [values]})."""
    reasons = []
    excluded = False
    adjustment = 0.0
    for req in method_requirements:
        status, detail = check(req, facts, ctx)
        change = effect(req, status)
        adjustment += change
        if req["strength"] == "hard" and status == "fail":
            excluded = True
        reasons.append({
            "requirement": req["id"],
            "label": req["label"],
            "strength": req["strength"],
            "status": status,
            "detail": detail,
            "effect": round(change, 3),
            "rationale": req["rationale"],
        })
    return {"excluded": excluded, "adjustment": round(adjustment, 3), "reasons": reasons}


def judge_methods(urr, methods: list[dict] | None = None) -> dict:
    """All requirements of the URR, and a verdict for every method.

    methods: the methods to judge (default: all methods of the URR's challenge).
    """
    all_requirements = requirements.collect(urr)
    method_requirements = [r for r in all_requirements if r["kind"] == "method"]
    all_facts = ontology.method_facts()
    ctx = build_context(urr, all_facts)

    verdicts = []
    if methods is None:
        methods = ontology.list_methods(urr.challenge)
    for method in methods:
        facts = all_facts.get(method["id"], {})
        verdict = judge(facts, method_requirements, ctx)
        verdicts.append({"id": method["id"], "label": method["label"], **verdict})

    return {
        "requirements": all_requirements,
        "methods": verdicts,
        "excluded": sum(1 for v in verdicts if v["excluded"]),
    }