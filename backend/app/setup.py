"""Modeling Approach entry: diagnose a modelling set-up and propose improvements.

The user starts from what they already use (one method, or a software and its methods)
and a study context (challenge + objective, optionally output, entity, ...). Two answers:

  diagnose   how well does this set-up fit the study?   -> checks, issues, a fit score
  improve    how can it be improved?                    -> actions, each with a 'patch'

The backend keeps nothing between calls: the frontend holds the request, merges the
patch of an accepted action into it and asks again.

Four paths of improvement:
  A  more data         add a dataset, derive a variable, add calibration data
  B  finer data        the same variable at a finer time step
  C  combine           add a method that feeds an input, fills a role or extends the output
  D  replace           another method for the same job, or a standard chain

Layering: setup.py -> knowledge.py, chains.py, timesteps.py, requirements.py, config.py.
"""
import hashlib
from typing import Literal

from pydantic import BaseModel, Field

from app import chains, config, knowledge, requirements, timesteps
from app.chains import get, ref, refs

BLOCKING, WARNING, INFO = "blocking", "warning", "info"
GAIN_ORDER = {"blocking": 0, "high": 1, "medium": 2, "low": 3}
EFFORT_ORDER = {"low": 0, "medium": 1, "high": 2}
CONSISTENCY = {"DUPLICATE_ROLE", "MODE_MIX", "STEP_CHAIN", "SPATIAL_MISMATCH"}


# ----------------------------------------------------------------------------
# Request
# ----------------------------------------------------------------------------

class Setup(BaseModel):
    software: str | None = None
    methods: list[str] = Field(default_factory=list)
    # which job each method does, when it can do several (Linear Reservoir: runoff
    # transform or baseflow). Missing = decided automatically.
    roles: dict[str, list[str]] = Field(default_factory=dict)
    reference_chain: str | None = None
    # components the user removed ON PURPOSE (method -> the jobs it had). The engine keeps
    # saying what is lost, but no longer proposes to put them back.
    left_out: dict[str, list[str]] = Field(default_factory=dict)


class Context(BaseModel):
    challenge: str
    objective: str
    intent: str | None = None
    scenario: str | None = None
    driver: str | None = None
    output: str | None = None          # a single output (older clients): merged into 'outputs'
    outputs: list[str] = Field(default_factory=list)
    output_step: str | None = None     # the time step the results are wanted at (hourly, daily...)
    entity: str | None = None
    region: str | None = None


class DataItem(BaseModel):
    variable: str
    source: Literal["own", "dataset"] = "own"
    dataset: str | None = None
    step: str | None = None
    resolution_m: float | None = None


class SetupRequest(BaseModel):
    setup: Setup
    context: Context
    data: list[DataItem] = Field(default_factory=list)
    lang: Literal["en", "fr"] = "en"


class OptionsRequest(BaseModel):
    """A request under construction: every part may still be missing."""

    step: str
    request: dict = Field(default_factory=dict)


class SetupError(Exception):
    """The request names something the ontology does not know."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def name(k, item_id: str) -> str:
    return k.labels.get(item_id) or item_id


def names(k, ids) -> str:
    return ", ".join(sorted(name(k, i) for i in ids))


def normalise(k, req: SetupRequest) -> tuple[SetupRequest, list[str]]:
    """Check every name, translate deprecated ones, fill the methods of a reference chain."""
    req = req.model_copy(deep=True)
    warnings: list[str] = []
    problems: list[str] = []

    def renamed(value: str | None) -> str | None:
        if value in k.replaced:
            warnings.append(f"Deprecated name {value} replaced by {k.replaced[value]}.")
            return k.replaced[value]
        return value

    req.context.entity = renamed(req.context.entity)

    chain = k.chains.get(req.setup.reference_chain) if req.setup.reference_chain else None
    if req.setup.reference_chain and chain is None:
        problems.append(f"Unknown reference chain: {req.setup.reference_chain}")
    if chain and not req.setup.methods:
        # a standard workflow starts with its ESSENTIAL components only; the optional ones
        # (interception, snow, a separate routing...) are recommended in the diagnosis
        outputs = list(dict.fromkeys(([req.context.output] if req.context.output else []) + req.context.outputs))
        essential, _ = chains.essential_split(k, chain["steps"], chain["template"], outputs)
        req.setup.methods = list(dict.fromkeys(s["method"] for s in essential))

    if not req.setup.methods:
        problems.append("The set-up needs at least one method.")
    for method in req.setup.methods:
        if method not in k.facts:
            problems.append(f"Unknown method: {method}")
    if req.setup.software and req.setup.software not in k.software:
        problems.append(f"Unknown software: {req.setup.software}")
    for method, roles in req.setup.roles.items():
        for role in roles:
            if role not in get(k, method, "fillsRole"):
                problems.append(f"{method} cannot fill the role {role}")

    c = req.context
    c.outputs = list(dict.fromkeys(([c.output] if c.output else []) + c.outputs))
    c.output = None
    if c.challenge not in k.challenges:
        problems.append(f"Unknown challenge: {c.challenge}")
    for field, kind in (("objective", "objective"), ("intent", "intent"), ("scenario", "scenario"),
                        ("driver", "driver"), ("entity", "entity")):
        value = getattr(c, field)
        if value is not None and value not in k.vocabulary[kind]:
            problems.append(f"Unknown {field}: {value}")
    for output in c.outputs:
        if output not in k.vocabulary["output"]:
            problems.append(f"Unknown output: {output}")
    if c.output_step and c.output_step not in k.hours:
        problems.append(f"Unknown time step: {c.output_step}")
    for item in req.data:
        if item.variable not in k.labels:
            problems.append(f"Unknown variable: {item.variable}")
        if item.step and item.step not in k.hours:
            problems.append(f"Unknown time step: {item.step}")

    if problems:
        raise SetupError(problems)
    if c.driver is None and k.default_driver.get(c.challenge):
        default = sorted(k.default_driver[c.challenge])[0]
        warnings.append(f"No driver given: using the default driver of the challenge, {name(k, default)}.")
    return req, warnings


# ----------------------------------------------------------------------------
# Roles of the set-up
# ----------------------------------------------------------------------------

def role_order(k) -> list[str]:
    """All roles from upstream to downstream (their usual position in the chain templates)."""
    positions: dict[str, list[int]] = {}
    for template in k.templates.values():
        for slot in template["slots"]:
            positions.setdefault(slot["role"], []).append(slot["order"])
    known = sorted(positions, key=lambda r: (sum(positions[r]) / len(positions[r]), r))
    return known + sorted(r for r in k.roles if r not in positions)


def assign_roles(k, setup: Setup) -> dict[str, list[str]]:
    """Which job(s) each method of the set-up does.

    1. the roles the request states;
    2. else the roles it has in the chosen reference chain;
    3. else every role it can fill, minus the roles another method of the set-up is
       there for (a method that can only do that job, or was given it explicitly).
    """
    chain = k.chains.get(setup.reference_chain) if setup.reference_chain else None
    assigned: dict[str, list[str]] = {}
    free: list[str] = []
    for method in setup.methods:
        fills = get(k, method, "fillsRole")
        if setup.roles.get(method):
            assigned[method] = list(setup.roles[method])
        elif chain and any(s["method"] == method for s in chain["steps"]):
            assigned[method] = [s["role"] for s in chain["steps"] if s["method"] == method]
        elif len(fills) <= 1:
            assigned[method] = list(fills)
        else:
            free.append(method)
    for method in free:
        taken = {r for other, roles in assigned.items() if other != method for r in roles}
        fills = get(k, method, "fillsRole")
        assigned[method] = [r for r in fills if r not in taken] or list(fills)
    return assigned


def placement(k, candidate: str, wanted: str | None, taken: set[str]) -> list[str] | None:
    """The jobs a method would take if it were added to a set-up, or None if it has no place.

    The rule that prevents overlap: a method is added either
      * in a job it is KNOWN to do on its own (as in a standard chain), or
      * with ALL its jobs,
    and every job it takes must be free. GR4J always does soil water budget, excess
    rainfall, transform and baseflow together: it cannot be added "as baseflow" next to
    a model that already does the other three.

    wanted: the job the set-up is missing (the smallest fitting use is taken), or None
    (the largest free use is taken).
    """
    fills = frozenset(get(k, candidate, "fillsRole"))
    uses = set(k.uses.get(candidate, set())) | {fills}
    if k.separability.get(candidate) == "separable":
        uses |= {frozenset([role]) for role in fills}
    free = [use for use in uses if use and not (use & taken) and (wanted is None or wanted in use)]
    if not free:
        return None
    best = min(free, key=lambda u: (len(u), sorted(u))) if wanted else max(free, key=lambda u: (len(u), sorted(u)))
    return sorted(best)


def software_scope(k, setup: Setup) -> set[str]:
    """The software the set-up lives in: the one chosen, plus those of its standard chain."""
    scope = {setup.software} if setup.software else set()
    chain = k.chains.get(setup.reference_chain) if setup.reference_chain else None
    if chain and (not scope or scope & chain["software"]):
        scope |= chain["software"]
    return scope


def inside_software(k, candidate: str, jobs: list[str], scope: set[str]) -> bool:
    """May this candidate be proposed, given the software of the set-up?

    An integrated software already has a module for most jobs. A method from ANOTHER
    software is proposed only for a job the software has no module for (an external
    coupling); otherwise the software's own methods are the candidates.
    """
    if not scope or scope & set(get(k, candidate, "canBeImplementedIn")):
        return True
    return not any(k.modules.get(software, {}).get(job) for software in scope for job in jobs)


# ----------------------------------------------------------------------------
# Requirement rules applied to a whole set-up
# ----------------------------------------------------------------------------

def collect_requirements(k, context: Context, in_hand: set[str]) -> list[dict]:
    """The requirements implied by the context (same engine as the Challenge entry)."""
    from types import SimpleNamespace

    problem = SimpleNamespace(
        challenge=context.challenge, objective=context.objective, intent=context.intent,
        scenario=context.scenario, entity=context.entity,
        drivers=[context.driver] if context.driver else [],
        outputs=list(context.outputs),
        available_variables=sorted(in_hand),
    )
    return requirements.collect(problem)


def judge_rule(k, req: dict, S: dict) -> tuple[str, str]:
    """One requirement against the set-up: ('pass' | 'fail' | 'unknown', detail)."""
    methods = S["methods"]
    rule = req["rule_id"]

    if req["on_property"] and not rule:
        prop, allowed = req["on_property"], set(req["allowed_values"])
        judged = []
        for m in methods:
            values = set(get(k, m, prop))
            if prop == "hasTemporalMode":
                values -= {"SteadyState"}          # steady-state components are neutral
            if values:
                judged.append((m, bool(values & allowed)))
        if not judged:
            return "unknown", f"{prop} is not recorded for the set-up"
        failing = [m for m, ok in judged if not ok]
        if not failing:
            return "pass", f"{prop}: every method allows {' or '.join(sorted(allowed))}"
        return "fail", f"{prop}: {names(k, failing)} need(s) {' or '.join(sorted(allowed))}"

    if rule == "produces-expected-output":
        if not S["outputs"]:
            return "unknown", "no output chosen"
        missing = set().union(*(k.output_variables.get(o, set()) for o in S["outputs"])) - S["outs"]
        return ("pass", "the set-up computes the output") if not missing else \
            ("fail", "does not compute " + names(k, missing))
    if rule == "produces-state-variable":
        states = S["outs"] & k.states
        return ("pass", "computes the state " + names(k, states)) if states else \
            ("fail", "computes no state variable")
    if rule == "spatially-distributed-output":
        return ("pass", "a distributed or 2D/3D method computes the output") if S["map_ok"] else \
            ("fail", "no fully distributed or 2D/3D method computes the output")
    if rule == "driver-variable-is-input":
        drivers = [S["driver"]] if S["driver"] else []
        if not drivers:
            return "unknown", "no driver to check"
        wanted = set().union(*(k.driver_variables.get(d, set()) for d in drivers))
        usable = set()
        for m in methods:
            usable |= set(get(k, m, "requiresMandatoryInput")) | set(get(k, m, "acceptsOptionalInput")) \
                | set(get(k, m, "hasPhysicalParameter"))
        return ("pass", "the driver is represented by " + names(k, wanted & usable)) if wanted & usable \
            else ("fail", "no variable of the driver is an input or physical parameter")
    if rule == "few-calibration-parameters":
        n = sum(len(get(k, m, "hasCalibrationParameter")) for m in methods)
        return ("pass" if n <= config.MAX_CALIBRATION_PARAMETERS else "fail"), f"{n} calibration parameter(s)"
    if rule == "physical-parameters-dominant":
        physical = sum(len(get(k, m, "hasPhysicalParameter")) for m in methods)
        calibrated = sum(len(get(k, m, "hasCalibrationParameter")) for m in methods)
        return ("pass" if physical >= calibrated else "fail"), \
            f"{physical} physical vs {calibrated} calibration parameters"
    if rule == "calibration-data-available":
        targets = set()
        for m in methods:
            targets |= set(get(k, m, "isCalibratedAgainst"))
        if not targets:
            return "unknown", "no calibration variable recorded"
        usable = targets & (S["in_hand"] | k.measured)
        return ("pass", "measured data for " + names(k, usable)) if usable else \
            ("fail", "no measured data for " + names(k, targets))
    return "unknown", f"rule '{rule}' is not evaluated on a set-up"


# ----------------------------------------------------------------------------
# Diagnosis
# ----------------------------------------------------------------------------

def diagnose(k, req: SetupRequest, reqs: list[dict] | None = None, warnings: list[str] | None = None) -> dict:
    """Judge the set-up in its study context. 'req' must come from normalise()."""
    setup, context = req.setup, req.context
    methods = list(dict.fromkeys(setup.methods))
    roles = assign_roles(k, setup)
    in_hand = {item.variable: item for item in req.data}
    issues: list[dict] = []
    checks: list[dict] = []

    def issue(code: str, severity: str, subject: str | None, message: str, detail: str = "",
              gain: str = "medium") -> None:
        issues.append({"code": code, "severity": severity, "gain_hint": gain,
                       "subject": subject, "message": message, "detail": detail})

    def check(check_id: str, title: str, codes: set[str], ok_message: str) -> None:
        found = [i for i in issues if i["code"] in codes]
        worst = "fail" if any(i["severity"] == BLOCKING for i in found) else \
            "warn" if any(i["severity"] == WARNING for i in found) else "ok"
        message = ok_message if not found else "; ".join(i["message"] for i in found[:3])
        checks.append({"id": check_id, "title": title, "status": worst, "message": message,
                       "detail": "; ".join(i["detail"] for i in found if i["detail"])})

    # ---- derived sets --------------------------------------------------------------
    order = role_order(k)
    steps = sorted(
        ({"method": m, "role": r, "software": setup.software} for m in methods for r in roles[m]),
        key=lambda s: order.index(s["role"]) if s["role"] in order else 99,
    ) or [{"method": m, "role": None, "software": setup.software} for m in methods]
    verdict = chains.evaluate(k, steps, chains.context(available=set(in_hand)), context.challenge)
    roles_filled = {r for m in methods for r in roles[m]}
    procs = set().union(*(set(get(k, m, "modelsProcess")) for m in methods))
    outs = verdict["produced"]
    primary = k.primary.get(context.challenge, set())
    secondary = k.secondary.get(context.challenge, set())

    # ---- check 0: the set-up is consistent (needs at least two methods) -------------
    if len(methods) > 1:
        for role in sorted(roles_filled):
            holders = [m for m in methods if role in roles[m]]
            if len(holders) > 1:
                issue("DUPLICATE_ROLE", BLOCKING, role,
                      f"{names(k, holders)} do the same job ({name(k, role)}): keep one.",
                      "one method per role", "high")
        # an integrated method used for only part of its jobs, while other methods do the rest
        for m in methods:
            rest = set(get(k, m, "fillsRole")) - set(roles[m])
            doers = sorted({o for o in methods if o != m and rest & set(roles[o])})
            if k.separability.get(m) == "integrated" and rest and rest <= roles_filled:
                issue("OVERLAP", WARNING, m,
                      f"{name(k, m)} is used here only as {names(k, roles[m])}, but it is a complete "
                      f"component that also does {names(k, rest)}: these are already done by "
                      f"{names(k, doers)}. The same water would be counted twice: remove it, or let it "
                      "replace them.", "integrated method sliced to part of its jobs", "high")
        modes_recorded = any(set(get(k, m, "hasTemporalMode")) - {"SteadyState"} for m in methods)
        if modes_recorded and not verdict["modes"]:
            issue("MODE_MIX", BLOCKING, None,
                  "The methods cannot run together: some are event-based only, others continuous only.",
                  "no shared temporal mode", "high")
        for conflict in verdict["conflicts"]:
            issue("STEP_CHAIN", BLOCKING, conflict["from"],
                  f"{name(k, conflict['from'])} cannot run as finely as {name(k, conflict['to'])} needs.",
                  "upstream time step coarser than downstream", "high")
        for interface in k.interfaces:
            for a in methods:
                for b in methods:
                    if a == b or interface["from"] not in roles[a] or interface["to"] not in roles[b]:
                        continue
                    if interface["variable"] not in get(k, a, "producesOutput"):
                        continue
                    # b must actually take what a gives (directly, or in place of one of its inputs)
                    b_takes = set(get(k, b, "requiresMandatoryInput")) | set(get(k, b, "acceptsOptionalInput")) \
                        | set(get(k, b, "requiresInitialCondition"))
                    if interface["variable"] not in b_takes and not (interface["substitutes"] & b_takes):
                        continue
                    if frozenset((a, b)) in k.chain_pairs:
                        continue                  # a standard chain uses them together: the link is known
                    if b not in get(k, a, "canFeed") and not any(
                            i["code"] == "NO_LINK" and i["subject"] == f"{a}>{b}" for i in issues):
                        issue("NO_LINK", WARNING, f"{a}>{b}",
                              f"The ontology records no direct link from {name(k, a)} to {name(k, b)}.",
                              "roles linked by an interface but no canFeed", "low")
                    spatial_b = set(get(k, b, "hasSpatialRepresentation"))
                    if interface["spatial_match"] and spatial_b == {"FullyDistributed"} \
                            and "FullyDistributed" not in get(k, a, "hasSpatialRepresentation"):
                        issue("SPATIAL_MISMATCH", BLOCKING, f"{a}>{b}",
                              f"{name(k, b)} is gridded and needs a gridded method before it; "
                              f"{name(k, a)} is not.", "matching spatial representation required", "high")
    check("consistency", "The methods work together", CONSISTENCY | {"NO_LINK", "OVERLAP"},
          "The methods of the set-up are compatible with each other." if len(methods) > 1
          else "A single method: nothing to check between methods.")

    # ---- check 1: processes covered ------------------------------------------------
    # what the user left out on purpose: still reported, never proposed again
    roles_left = {r for held in setup.left_out.values() for r in held} - roles_filled
    processes_left = set().union(*(set(get(k, m, "modelsProcess")) for m in setup.left_out)) - procs \
        if setup.left_out else set()
    for process in sorted(primary - procs):
        chosen = process in processes_left
        issue("MISSING_PRIMARY_PROCESS", WARNING, process,
              f"A main process of {name(k, context.challenge)} is not modelled: {name(k, process)}"
              + (" (you left it out on purpose)." if chosen else "."),
              "primary process not covered", "high")
        issues[-1]["accepted"] = chosen
    for process in sorted(secondary - procs):
        issue("MISSING_SECONDARY_PROCESS", INFO, process,
              f"A secondary process is not modelled: {name(k, process)}.", "", "medium")
    coverage_primary = round(len(procs & primary) / len(primary), 3) if primary else 1.0
    coverage_secondary = round(len(procs & secondary) / len(secondary), 3) if secondary else 1.0
    check("processes", "Processes of the challenge", {"MISSING_PRIMARY_PROCESS"},
          "Every main process of the challenge is modelled.")

    # ---- output facts (used by the rules and by check 3) ------------------------------
    outputs = list(context.outputs)

    def output_facts(output: str) -> tuple[set[str], bool]:
        """The variables behind one output, and whether the set-up can draw it (a map needs a grid)."""
        expressed = k.output_variables.get(output, set())
        needs_map = "MapForm" in k.output_forms.get(output, set())
        producers = [m for m in methods if expressed & set(get(k, m, "producesOutput"))]
        return expressed, not needs_map or any(
            "FullyDistributed" in get(k, m, "hasSpatialRepresentation")
            or set(get(k, m, "hasDimensionality")) & {"Dim2D", "Dim3D"} for m in producers)

    facts_of = {o: output_facts(o) for o in outputs}
    map_ok = all(ok for _, ok in facts_of.values())
    driver = context.driver or next(iter(sorted(k.default_driver.get(context.challenge, set()))), None)

    # ---- check 2: study objective and requirements ------------------------------------
    if reqs is None:
        reqs = collect_requirements(k, context, set(in_hand))
    S = {"methods": methods, "outs": outs, "in_hand": set(in_hand), "outputs": outputs,
         "driver": driver, "map_ok": map_ok}
    rule_results = []
    for requirement in reqs:
        if requirement["kind"] != "method":
            continue
        if requirement["rule_id"] in ("produces-expected-output", "spatially-distributed-output"):
            continue                                   # check 3 covers the output
        status, detail = judge_rule(k, requirement, S)
        rule_results.append({"requirement": requirement["id"], "label": requirement["label"],
                             "strength": requirement["strength"], "status": status, "detail": detail,
                             "rationale": requirement["rationale"]})
        if status == "fail":
            hard = requirement["strength"] == "hard"
            issue("RULE_FAILED", BLOCKING if hard else WARNING, requirement["id"],
                  requirement["rationale"] or requirement["label"] or requirement["id"], detail,
                  "high" if hard else "medium")
    fine_step_wanted = any(r["id"] == "Req_FineTimeStep" for r in reqs) \
        or context.objective == "ThresholdDetection" or context.intent == "Detection" \
        or "PeakFlow" in outputs
    if not outputs:
        suggested = sorted(k.typical_outputs.get(context.challenge, set()),
                           key=lambda o: (o not in k.primary_outputs.get(context.challenge, set()), o))[:3]
        issue("NO_OUTPUT", INFO, None,
              "No expected output chosen. Usual ones for this challenge: " + names(k, suggested) + ".",
              "", "low")
    check("objective", "Study objective and requirements", {"RULE_FAILED"},
          "The set-up meets what the study objective requires.")

    # ---- check 3: can the set-up deliver the output? ---------------------------------
    serving = [t for t in k.templates.values() if context.challenge in t["serves"]]
    output_rows: list[dict] = []
    # what the set-up delivers: what its methods compute, plus what derives from it
    # (runoff volume is the time integral of the discharge the set-up computes)
    reach, via = knowledge.closure(k, outs)
    for output in outputs:
        expressed, drawable = facts_of[output]
        missing_variables = expressed - reach
        status = "delivered"
        if missing_variables or not drawable:
            template_way = any(
                output in t["delivers"] and roles_filled & {s["role"] for s in t["slots"]}
                for t in k.templates.values())
            feed_way = any(
                missing_variables and missing_variables <= set(get(k, b, "producesOutput"))
                for m in methods for b in get(k, m, "canFeed"))
            what = names(k, missing_variables) if missing_variables else "a map (needs a distributed or 2D/3D method)"
            if template_way or feed_way:
                status = "needs_combination"
                issue("OUTPUT_NEEDS_COMBINATION", BLOCKING, output,
                      f"The set-up alone does not deliver {name(k, output)}: another method "
                      f"must be added to compute {what}.", "output variables: " + names(k, expressed), "high")
            else:
                status = "unreachable"
                issue("OUTPUT_UNREACHABLE", BLOCKING, output,
                      f"This set-up cannot lead to {name(k, output)}, even combined with "
                      "other methods.", "no template or downstream method delivers it", "high")
        needs_grid = "MapForm" in k.output_forms.get(output, set())
        gridded = [m for m in methods if "FullyDistributed" in get(k, m, "hasSpatialRepresentation")
                   or set(get(k, m, "hasDimensionality")) & {"Dim2D", "Dim3D"}]
        output_rows.append({**ref(k, output), "question": k.questions.get(output), "status": status,
                            "definition": k.definitions.get(output),
                            "forms": [{**ref(k, f), "definition": k.definitions.get(f)}
                                      for f in sorted(k.output_forms.get(output, set()))],
                            # the trace: output <- variables <- the method computing each one
                            "trace": [{
                                **v,
                                "computed_by": [ref(k, m) for m in methods if v["id"] in get(k, m, "producesOutput")],
                                "gridded_by": [ref(k, m) for m in gridded if v["id"] in get(k, m, "producesOutput")],
                                "derivations": chains.derivations(k, v["id"]),
                                # not computed as such, but obtained from what the set-up computes
                                "derived": None if v["id"] in outs or v["id"] not in via else {
                                    "from": refs(k, via[v["id"]]["inputs"]), "how": via[v["id"]]["method"],
                                    "computed_by": [ref(k, m) for m in methods
                                                    if via[v["id"]]["inputs"] & set(get(k, m, "producesOutput"))]},
                            } for v in refs(k, expressed)],
                            "needs_grid": needs_grid, "drawable": drawable,
                            "variables": refs(k, expressed), "missing": refs(k, missing_variables),
                            "produced_by": [m for m in methods if expressed & set(get(k, m, "producesOutput"))]})
    if context.output_step:
        wanted_variables = set().union(*(facts[0] for facts in facts_of.values())) if facts_of else set()
        givers = [m for m in methods if wanted_variables & set(get(k, m, "producesOutput"))] or methods
        for m in givers:
            if not timesteps.can_deliver(k.hours, get(k, m, "supportsTimeStep"), context.output_step):
                finest = timesteps.order(k.hours, get(k, m, "supportsTimeStep"))[:1]
                issue("OUTPUT_STEP", WARNING, m,
                      f"{name(k, m)} cannot give {name(k, context.output_step)} results"
                      + (f": its finest time step is {name(k, finest[0])}." if finest else "."),
                      "method coarser than the time step wanted for the results", "high")
    check("output", "Expected output", {"OUTPUT_NEEDS_COMBINATION", "OUTPUT_UNREACHABLE", "NO_OUTPUT", "OUTPUT_STEP"},
          "The set-up computes every expected output." if len(outputs) > 1
          else "The set-up computes the expected output.")

    # ---- check 4: roles of the best template -----------------------------------------
    wanted = set(outputs)                 # a template delivering every output, else some of them
    candidates = [t for t in serving if wanted <= t["delivers"]] \
        or [t for t in serving if wanted & t["delivers"]] or serving
    best = None
    if candidates:
        def quality(t: dict):
            slot_roles = {s["role"] for s in t["slots"]}
            missing = {s["role"] for s in t["slots"] if s["mandatory"]} - roles_filled
            has_chain = any(c["template"] == t["id"] for c in k.chains.values())
            return (len(missing), -len(slot_roles & roles_filled), not has_chain, t["id"])
        best = min(candidates, key=quality)
        for slot in best["slots"]:
            if slot["mandatory"] and slot["role"] not in roles_filled:
                chosen = slot["role"] in roles_left
                issue("MISSING_ROLE", WARNING, slot["role"],
                      f"A usual component is missing: {name(k, slot['role'])} "
                      f"({k.role_definitions.get(slot['role']) or 'no definition'})"
                      + (" You left it out on purpose." if chosen else "."),
                      f"mandatory slot of {name(k, best['id'])}", "high")
                issues[-1]["accepted"] = chosen
    check("roles", "Components of a complete model", {"MISSING_ROLE"},
          "Every mandatory component of the usual workflow is present.")

    # ---- check 5: data ------------------------------------------------------------------
    data_rows: list[dict] = []

    def users_of(variable: str, prop: str) -> list[str]:
        return [m for m in methods if variable in get(k, m, prop)]

    def fine_datasets(variable: str, users: list[str]) -> list[dict]:
        """Datasets providing the variable finely enough for the methods that take it (rule C)."""
        found: dict[str, dict] = {}
        for source in k.data.get(variable, []):
            if not source["dataset"]:
                continue
            if all(timesteps.dataset_ok(k.hours, source["step"], get(k, m, "supportsTimeStep")) for m in users):
                entry = found.setdefault(source["dataset"], {**ref(k, source["dataset"]), "steps": [],
                                                             "measured": False})
                if source["step"] and source["step"] not in entry["steps"]:
                    entry["steps"].append(source["step"])
                entry["measured"] = entry["measured"] or source["provenance"] in ("Observed", "RemoteSensingRetrieval")
        return list(found.values())

    def row(variable: str, kind: str, users: list[str]) -> dict:
        # calibration data may be coarser than the method: its results are aggregated (rule B)
        # ... and a static description (land cover, terrain) is not bound by the time step at all
        relaxed = kind in ("calibration", "parameter") or variable in k.static
        datasets = fine_datasets(variable, [] if relaxed else users)
        derivable = variable in k.derived_from
        # a data variable is recorded, but no dataset is linked to it in the catalogue
        unlinked = variable in k.data and not any(s["dataset"] for s in k.data[variable])
        by_component = any(
            i["to"] in roles[m] and (i["variable"] == variable or variable in i["substitutes"])
            for m in users for i in k.interfaces)
        if variable in in_hand:
            status = "in_hand"
        elif kind == "initial":
            status = "initial_state"
        elif kind == "optional":
            status = "unused"
        elif datasets or unlinked:
            status = "available"
        elif derivable:
            status = "derivable"
        elif kind == "mandatory" and by_component:
            status = "needs_component"
        else:
            status = "missing"
        item = in_hand.get(variable)
        entry = {
            **ref(k, variable), "kind": kind, "status": status,
            "nature": chains.input_kind(k, variable, users[0] if users else None),
            "time_varying": variable not in k.static and kind != "initial",
            "used_by": [ref(k, m) for m in users],
            "datasets": [{**d, "url": k.dataset_urls.get(d["id"])}
                         for d in sorted(datasets, key=lambda d: (not d["measured"], d["label"] or d["id"]))],
            "derivations": chains.derivations(k, variable),
            "derived_from": refs(k, k.derived_from.get(variable, set())),
            "step": item.step if item else None,
            "step_ref": ref(k, item.step) if item and item.step else None,
            "source": item.source if item else None,
            "dataset": {**ref(k, item.dataset), "url": k.dataset_urls.get(item.dataset)}
            if item and item.dataset else None,
        }
        data_rows.append(entry)
        return entry

    external = sorted(set().union(*verdict["external"].values())) if verdict["external"] else []
    for variable in external:
        users = [m for m in methods if variable in verdict["external"][m]]
        entry = row(variable, "mandatory", users)
        label = name(k, variable)
        if entry["status"] == "available":
            issue("DATA_AVAILABLE", INFO, variable, f"{label}: an open dataset can provide it.", "", "medium")
        elif entry["status"] == "derivable":
            issue("DATA_DERIVABLE", INFO, variable,
                  f"{label} can be derived from {names(k, k.derived_from[variable])}.", "", "medium")
        elif entry["status"] == "needs_component":
            issue("MISSING_INPUT_COMPONENT", BLOCKING, variable,
                  f"{label} has no usable data source: another method must compute it "
                  f"for {names(k, users)}.", "an interface can supply it", "high")
        elif entry["status"] == "missing":
            issue("MISSING_INPUT", BLOCKING, variable, f"{label} is required and has no source.", "", "high")

    calibrated = [m for m in methods if get(k, m, "hasCalibrationParameter")]
    targets = sorted(set().union(*(set(get(k, m, "isCalibratedAgainst")) for m in calibrated))) if calibrated else []
    target_rows = [row(v, "calibration", users_of(v, "isCalibratedAgainst")) for v in targets if v not in external]
    if calibrated and targets:
        usable = [v for v in targets if v in in_hand or v in k.measured]
        if not usable:
            issue("NO_CALIBRATION_DATA", WARNING, None,
                  "No measured data to calibrate the set-up against (" + names(k, targets) + ").", "", "high")
        elif not any(v in in_hand for v in targets):
            for entry in target_rows:
                if entry["status"] == "available":
                    issue("DATA_AVAILABLE", INFO, entry["id"],
                          f"{entry['label'] or entry['id']}: measured open data exists to calibrate against.",
                          "", "high")

    optional = sorted(set().union(*(set(get(k, m, "acceptsOptionalInput")) for m in methods)) - set(external) - outs)
    for variable in optional:
        entry = row(variable, "optional", users_of(variable, "acceptsOptionalInput"))
        if entry["status"] == "unused":
            issue("OPTIONAL_UNUSED", INFO, variable,
                  f"Optional input not used: {name(k, variable)} would improve the result.", "", "medium")
    for item in verdict["initial_conditions"]:
        row(item["id"], "initial", users_of(item["id"], "requiresInitialCondition"))
        issue("INITIAL_STATE", INFO, item["id"],
              f"Initial state needed: {name(k, item['id'])}. Use a warm-up period or an observed snapshot.",
              "not missing data", "low")
    for item in verdict["parameters"]:
        entry = row(item["id"], "parameter", users_of(item["id"], "hasPhysicalParameter"))
        if entry["status"] == "missing":
            issue("MISSING_PARAMETER", WARNING, item["id"],
                  f"No source for the parameter {name(k, item['id'])}.", "", "medium")

    # time step of the data in hand
    for variable, item in in_hand.items():
        if variable in k.static:
            continue
        takers = [m for m in methods if variable in get(k, m, "requiresMandatoryInput")
                  or variable in get(k, m, "acceptsOptionalInput")]
        if not takers:
            continue
        label = name(k, variable)
        if not item.step:
            issue("STEP_UNKNOWN", INFO, variable,
                  f"Give the time step of your {label} data to check it fits the method.", "", "low")
            continue
        for m in takers:
            supports = get(k, m, "supportsTimeStep")
            if not timesteps.usable_as_is(k.hours, supports, item.step):
                issue("STEP_TOO_COARSE", BLOCKING, variable,
                      f"Your {name(k, item.step)} {label} is too coarse for {name(k, m)}: "
                      + timesteps.DISAGGREGATION_WARNING, "rule A: needs disaggregation", "high")
            elif any(k.hours[s] < k.hours[item.step] for s in supports if s in k.hours):
                finer = timesteps.order(k.hours, [s for s in supports if k.hours.get(s, 1e9) < k.hours[item.step]])
                issue("STEP_COULD_BE_FINER", WARNING if fine_step_wanted else INFO, variable,
                      f"{name(k, m)} can run at a finer step ({names(k, finer)}) than your "
                      f"{name(k, item.step)} {label}"
                      + (": your study needs fine time steps." if fine_step_wanted else "."),
                      "", "high" if fine_step_wanted else "low")
            break
    check("data", "Data", {"MISSING_INPUT", "MISSING_INPUT_COMPONENT", "STEP_TOO_COARSE", "NO_CALIBRATION_DATA",
                           "STEP_COULD_BE_FINER", "MISSING_PARAMETER"},
          "Every required input has a source.")

    # ---- fit summary ------------------------------------------------------------------
    blocking = sum(1 for i in issues if i["severity"] == BLOCKING)
    high = sum(1 for i in issues if i["severity"] == WARNING and i["gain_hint"] == "high")
    other = sum(1 for i in issues if i["severity"] == WARNING and i["gain_hint"] != "high")
    info = sum(1 for i in issues if i["severity"] == INFO)
    penalty = config.FIT_PENALTY
    score = max(0, config.FIT_START - penalty["blocking"] * blocking - penalty["warning_high"] * high
                - penalty["warning"] * other - penalty["info"] * info)
    if blocking == 0 and score >= config.FIT_GOOD:
        fit_label = "fit"
    elif blocking <= 2 or score >= config.FIT_PARTLY:
        fit_label = "partly fit"
    else:
        fit_label = "poor fit"
    study = f"{name(k, context.challenge)} {name(k, context.objective)}"
    message = f"{fit_label.capitalize()} for {study}: {blocking} blocking issue(s), {high + other} improvement(s)."

    for entry in issues:
        entry["key"] = f"{entry['code']}:{entry['subject'] or ''}"
    severity_rank = {BLOCKING: 0, WARNING: 1, INFO: 2}
    issues.sort(key=lambda i: (severity_rank[i["severity"]], GAIN_ORDER.get(i["gain_hint"], 9)))

    # what passes from one method of the set-up to the next (drawn by the frontend)
    position = {}
    for index, chain_step in enumerate(steps):
        position.setdefault(chain_step["method"], index)

    def takes(method: str) -> set[str]:
        return set(get(k, method, "requiresMandatoryInput")) | set(get(k, method, "acceptsOptionalInput"))

    links = []
    for a in methods:
        for b in methods:
            if a == b or position.get(a, 0) > position.get(b, 0):
                continue
            passed = set(get(k, a, "producesOutput")) & takes(b)
            for interface in k.interfaces:
                if interface["from"] in roles[a] and interface["to"] in roles[b] \
                        and interface["variable"] in get(k, a, "producesOutput") and b in get(k, a, "canFeed"):
                    passed.add(interface["variable"])
            if passed and not any(link["from"] == b and link["to"] == a for link in links):
                needed = set(get(k, b, "requiresMandatoryInput")) | set(get(k, b, "requiresInitialCondition"))
                for interface in k.interfaces:      # received in place of a required input
                    if interface["to"] in roles[b] and interface["variable"] in passed \
                            and interface["substitutes"] & needed:
                        needed.add(interface["variable"])
                links.append({"from": a, "to": b, "variables": refs(k, passed),
                              # the exchange is optional when the receiver runs without all of it
                              "optional": refs(k, passed - needed),
                              "optional_only": not (passed & needed)})

    # the software each method runs in: its step in the standard workflow, else the chosen one
    chain = k.chains.get(setup.reference_chain) if setup.reference_chain else None
    def software_of(m: str) -> str | None:
        if chain:
            for chain_step in chain["steps"]:
                if chain_step["method"] == m:
                    return chain_step["software"]
        if setup.software and setup.software in get(k, m, "canBeImplementedIn"):
            return setup.software
        own = get(k, m, "canBeImplementedIn")
        return own[0] if len(own) == 1 else None

    # which methods are essential (see chains.essential_split) and which are optional
    essential_methods, _ = chains.essential_split(k, steps, best["id"] if best else None, outputs)
    essential_set = {x["method"] for x in essential_methods}

    return {
        "study": {
            "challenge": ref(k, context.challenge), "objective": ref(k, context.objective),
            "intent": ref(k, context.intent), "scenario": ref(k, context.scenario),
            "entity": ref(k, context.entity), "driver": ref(k, driver),
            "driver_assumed": context.driver is None and driver is not None,
            "output_step": ref(k, context.output_step),
        },
        "links": links,
        "fit": {"label": fit_label, "score": score, "message": message, "blocking": blocking,
                "warnings": high + other, "infos": info},
        "setup": {
            "software": ref(k, setup.software),
            "reference_chain": ref(k, setup.reference_chain),
            "left_out": [{**ref(k, m), "roles": [ref(k, r) for r in held]}
                         for m, held in setup.left_out.items() if m not in methods],
            "methods": [
                {**ref(k, m), "roles": [ref(k, r) for r in roles[m]],
                 "can_also": [ref(k, r) for r in get(k, m, "fillsRole") if r not in roles[m]],
                 "delivers": refs(k, get(k, m, "producesOutput")),
                 "software": refs(k, get(k, m, "canBeImplementedIn")),
                 "runs_in": ref(k, software_of(m)),
                 "module": chains.module(k, software_of(m), m),
                 # essential: the study cannot do without it; optional: its effect can be neglected
                 "essential": m in essential_set}
                for m in sorted(methods, key=lambda m: position.get(m, 99))
            ],
        },
        "coverage": {"primary": coverage_primary, "secondary": coverage_secondary,
                     "processes": refs(k, procs), "roles_filled": [ref(k, r) for r in order if r in roles_filled]},
        "best_template": None if best is None else {
            **ref(k, best["id"]),
            "slots": [
                {"role": ref(k, s["role"]), "mandatory": s["mandatory"],
                 "filled_by": [ref(k, m) for m in methods if s["role"] in roles[m]]}
                for s in best["slots"]
            ],
        },
        "outputs": output_rows,
        "checks": checks,
        "rules": rule_results,
        "issues": issues,
        "data": data_rows,
        "presentation": [r["rule_id"] for r in reqs if r["kind"] == "presentation" and r["rule_id"]],
        "warnings": list(warnings or []),
    }


# ----------------------------------------------------------------------------
# Improvement
# ----------------------------------------------------------------------------

def apply_patch(req: SetupRequest, patch: dict) -> SetupRequest:
    """Merge the patch of an action into a copy of the request (the frontend does the same)."""
    body = req.model_dump()
    for key, value in patch.items():
        if key == "data+":                       # add (or replace) data items, by variable
            variables = {item["variable"] for item in value}
            body["data"] = [d for d in body["data"] if d["variable"] not in variables] + value
        elif key == "setup.methods+":
            body["setup"]["methods"] += [m for m in value if m not in body["setup"]["methods"]]
        elif key == "setup.methods-":
            body["setup"]["methods"] = [m for m in body["setup"]["methods"] if m not in value]
            for m in value:
                body["setup"]["roles"].pop(m, None)
        elif key == "setup.roles+":
            body["setup"]["roles"].update(value)
        elif key == "setup.left_out+":           # a component the user leaves out on purpose
            body["setup"]["left_out"].update(value)
        elif key == "setup.left_out-":           # ... and puts back
            for m in value:
                body["setup"]["left_out"].pop(m, None)
        elif key == "setup":                     # a whole new set-up
            body["setup"] = {**body["setup"], **value}
    return SetupRequest(**body)


def best_datasets(k, entry: dict, measured_only: bool = False) -> list[dict]:
    """Datasets for one data row, the most suitable first (measured data, then by name)."""
    found = [d for d in entry["datasets"] if d["measured"] or not measured_only]
    return found[:config.MAX_PER_KIND]


def coarsest_usable_step(k, dataset: dict, entry: dict) -> str | None:
    steps = timesteps.order(k.hours, dataset["steps"])
    return steps[0] if steps else None


def improve(k, req: SetupRequest, warnings: list[str] | None = None) -> dict:
    """The diagnosis, and the actions that would improve the set-up, the most useful first."""
    reqs = collect_requirements(k, req.context, {d.variable for d in req.data})
    before = diagnose(k, req, reqs, warnings)
    setup, context = req.setup, req.context
    methods = list(dict.fromkeys(setup.methods))
    roles = assign_roles(k, setup)
    roles_filled = {r for m in methods for r in roles[m]}
    issues = {i["key"]: i for i in before["issues"]}
    rows = {(d["id"], d["kind"]): d for d in before["data"]}
    proposals: list[dict] = []

    def propose(path: str, kind: str, subject: str | None, message: str, detail: str, proposal: dict,
                patch: dict, effort: str, gain: str = "low", advice: bool = False,
                standard: bool | None = None) -> None:
        proposals.append({"path": path, "kind": kind, "subject": subject, "message": message,
                          "detail": detail, "proposal": proposal, "patch": patch, "effort": effort,
                          "gain": gain, "advice": advice, "standard_practice": standard})

    def coupling_effort(candidate: str, interface_coupling: str | None = None) -> tuple[str, str]:
        """Effort of adding a method, from how it would be coupled to the set-up."""
        shared = set(get(k, candidate, "canBeImplementedIn"))
        internal = (setup.software in shared) if setup.software else all(
            shared & set(get(k, m, "canBeImplementedIn")) for m in methods)
        if internal:
            return "low", "runs in the same software"
        level = 2 if interface_coupling == "TwoWayCoupling" else 1
        own = sorted(shared)
        paid = own and not any(k.software.get(s, {}).get("free") or k.software.get(s, {}).get("open") for s in own)
        level = min(2, level + (1 if paid else 0))
        return ["low", "medium", "high"][level], \
            ("two-way coupling with " if level == 2 and not paid else "file exchange with ") + (names(k, own) or "another tool")

    scope = software_scope(k, setup)

    def add_method(candidate: str, role: str | None = None, taken: set[str] | None = None) -> dict | None:
        """Patch adding one method in a job it can really take, or None if it would overlap.

        See placement(): a method is added in a job it is known to do on its own, or with
        all its jobs, and only in free jobs. And see inside_software(): inside an integrated
        software, a job the software has a module for is filled from that software.
        """
        jobs = placement(k, candidate, role, roles_filled if taken is None else taken)
        if jobs is None:
            return None
        if not inside_software(k, candidate, jobs, scope) and not standard_partner(candidate, jobs):
            return None
        return {"setup.methods+": [candidate], "setup.roles+": {candidate: jobs}}

    def standard_partner(candidate: str, jobs: list[str]) -> bool:
        """Is the candidate, in these jobs, coupled to a method of the set-up in a standard chain?

        HEC-HMS has its own hydraulics option, yet the usual practice is to pass its
        hydrograph to HEC-RAS 2D. Such an external coupling stays proposed, next to the
        software's own option.
        """
        for chain in k.chains.values():
            held = {s["role"] for s in chain["steps"] if s["method"] == candidate}
            if held and held == set(jobs) and {s["method"] for s in chain["steps"]} & set(methods):
                return True
        return False

    def consistent(patch: dict | None) -> dict | None:
        """The diagnosis after the patch, or None if the methods no longer work together."""
        if patch is None:                       # the candidate has no place in the set-up
            return None
        after = diagnose(k, apply_patch(req, patch), reqs)
        new = {i["key"] for i in after["issues"] if i["code"] in CONSISTENCY | {"OVERLAP"}} - set(issues)
        return None if new else after

    def shares_software(candidate: str) -> bool:
        software = set(get(k, candidate, "canBeImplementedIn"))
        return (setup.software in software) if setup.software else any(
            software & set(get(k, m, "canBeImplementedIn")) for m in methods)

    def linked(candidate: str) -> bool:
        return any(candidate in get(k, m, "canFeed") or m in get(k, candidate, "canFeed") for m in methods)

    # methods used together with a set-up method in a standard chain: proposed first
    usual = set()
    for chain in k.chains.values():
        chain_methods = {s["method"] for s in chain["steps"]}
        if chain_methods & set(methods):
            usual |= chain_methods

    def ranked(candidates) -> list[str]:
        return sorted(set(candidates) - set(methods),
                      key=lambda c: (not shares_software(c), c not in usual, name(k, c)))

    # ---- path A: more data ----------------------------------------------------------
    for (variable, kind), entry in rows.items():
        label = entry["label"] or variable
        if entry["status"] == "available" and kind in ("mandatory", "calibration"):
            for dataset in best_datasets(k, entry, measured_only=kind == "calibration"):
                step = coarsest_usable_step(k, dataset, entry)
                what = "add_calibration_data" if kind == "calibration" else "add_dataset_mandatory"
                why = "to calibrate against" if kind == "calibration" else "as input"
                propose("more_data", what, variable,
                        f"Use {dataset['label'] or dataset['id']} for {label} ({why}).",
                        "measured data" if dataset["measured"] else "modelled or reanalysis data",
                        {"variable": ref(k, variable), "dataset": ref(k, dataset["id"]), "step": ref(k, step)},
                        {"data+": [{"variable": variable, "source": "dataset", "dataset": dataset["id"],
                                    "step": step, "resolution_m": None}]},
                        "low", "high" if kind == "calibration" else "medium")
        elif entry["status"] == "derivable":
            inputs = k.derived_from[variable]
            ready = all(i in {d.variable for d in req.data} or i in k.data for i in inputs)
            propose("more_data", "derive_variable", variable,
                    f"Derive {label} from {names(k, inputs)}.", "a derivation is recorded in the ontology",
                    {"variable": ref(k, variable), "from": refs(k, inputs)},
                    {"data+": [{"variable": variable, "source": "own", "dataset": None, "step": None,
                                "resolution_m": None}]},
                    "low" if ready else "medium", "medium")
        elif entry["status"] == "unused" and entry["datasets"]:
            dataset = entry["datasets"][0]
            step = coarsest_usable_step(k, dataset, entry)
            propose("more_data", "add_optional_input", variable,
                    f"Add the optional input {label} from {dataset['label'] or dataset['id']}.", "",
                    {"variable": ref(k, variable), "dataset": ref(k, dataset["id"])},
                    {"data+": [{"variable": variable, "source": "dataset", "dataset": dataset["id"],
                                "step": step, "resolution_m": None}]},
                    "low", "medium")
        elif entry["status"] == "initial_state":
            propose("more_data", "initial_state", variable,
                    f"Initial state {label}: run a warm-up period before the period of interest, "
                    "or start from an observed snapshot.", "advice only", {"variable": ref(k, variable)},
                    {}, "low", "low", advice=True)

    # ---- path B: finer data -----------------------------------------------------------
    for item in req.data:
        too_coarse = f"STEP_TOO_COARSE:{item.variable}" in issues
        if not (too_coarse or f"STEP_COULD_BE_FINER:{item.variable}" in issues) or not item.step:
            continue
        takers = [m for m in methods if item.variable in get(k, m, "requiresMandatoryInput")
                  or item.variable in get(k, m, "acceptsOptionalInput")]
        finer: dict[str, str] = {}
        for source in k.data.get(item.variable, []):
            if source["dataset"] and source["step"] and k.hours[source["step"]] < k.hours[item.step] \
                    and all(timesteps.dataset_ok(k.hours, source["step"], get(k, m, "supportsTimeStep"))
                            and timesteps.usable_as_is(k.hours, get(k, m, "supportsTimeStep"), source["step"])
                            for m in takers):
                finer.setdefault(source["dataset"], source["step"])
        label = name(k, item.variable)
        for dataset, step in sorted(finer.items())[:config.MAX_PER_KIND]:
            propose("finer_data", "finer_time_step", item.variable,
                    f"Replace your {name(k, item.step)} {label} with {name(k, dataset)} ({name(k, step)}).",
                    "same variable at a finer time step the method supports",
                    {"variable": ref(k, item.variable), "dataset": ref(k, dataset), "step": ref(k, step)},
                    {"data+": [{"variable": item.variable, "source": "dataset", "dataset": dataset,
                                "step": step, "resolution_m": None}]},
                    "low", "blocking" if too_coarse else "high")
        if too_coarse and not finer:
            propose("finer_data", "disaggregate", item.variable,
                    f"No finer open dataset for {label}: get finer measurements, or disaggregate "
                    "your data knowing it biases intensity-driven processes.", "advice only",
                    {"variable": ref(k, item.variable)}, {}, "high", "blocking", advice=True)

    # ---- path C: combine ----------------------------------------------------------------
    for key, found in issues.items():
        if found["code"] != "MISSING_INPUT_COMPONENT":
            continue
        variable = found["subject"]
        users = [m for m in methods if variable in get(k, m, "requiresMandatoryInput")]
        options: dict[str, tuple[str, str | None, str]] = {}
        for m in users:
            for interface in k.interfaces:
                if interface["to"] not in roles[m] or not (
                        interface["variable"] == variable or variable in interface["substitutes"]):
                    continue
                for a in k.facts:
                    if interface["from"] in get(k, a, "fillsRole") and m in get(k, a, "canFeed") \
                            and interface["variable"] in get(k, a, "producesOutput"):
                        options.setdefault(a, (interface["from"], interface["coupling"], interface["variable"]))
        kept = 0
        for a in ranked(options):
            role, coupling, passed = options[a]
            patch = add_method(a, role)
            if consistent(patch) is None:
                continue
            effort, how = coupling_effort(a, coupling)
            propose("combine", "feed_input", variable,
                    f"Add {name(k, a)} before {names(k, users)}: it computes {name(k, variable)}.",
                    f"{name(k, role)}; {how}",
                    {"method": ref(k, a), "role": ref(k, role), "variable": ref(k, variable),
                     "passes": ref(k, passed), "to": [ref(k, m) for m in users]},
                    patch, effort, "blocking", standard=False)
            kept += 1
            if kept == config.MAX_PER_KIND:
                break

    for need_output in [i for i in issues.values() if i["code"] == "OUTPUT_NEEDS_COMBINATION"]:
        output = need_output["subject"]
        expressed = k.output_variables.get(output, set())
        produced = set().union(*(set(get(k, m, "producesOutput")) for m in methods))
        missing = expressed - knowledge.closure(k, produced)[0]
        needs_map = "MapForm" in k.output_forms.get(output, set())

        def delivers(method: str) -> bool:
            ok_map = not needs_map or "FullyDistributed" in get(k, method, "hasSpatialRepresentation") \
                or bool(set(get(k, method, "hasDimensionality")) & {"Dim2D", "Dim3D"})
            wanted = missing or expressed
            # with the candidate, every missing variable is computed or derives from what is computed
            return wanted <= knowledge.closure(k, produced | set(get(k, method, "producesOutput")))[0] \
                and bool(wanted & knowledge.closure(k, set(get(k, method, "producesOutput")))[0]) and ok_map

        fed = {b for m in methods for b in get(k, m, "canFeed")}
        kept = 0
        for b in ranked(c for c in fed if delivers(c)):
            patch = add_method(b)
            if consistent(patch) is None:
                continue
            effort, how = coupling_effort(b, "OfflineOneWay")
            propose("combine", "extend_output", output,
                    f"Add {name(k, b)} after the set-up to deliver {name(k, output)}.",
                    f"{names(k, get(k, b, 'fillsRole'))}; {how}",
                    {"methods": [ref(k, b)], "output": ref(k, output)}, patch, effort, "blocking",
                    standard=False)
            kept += 1
            if kept == config.MAX_PER_KIND:
                break
        if kept == 0:                                     # two steps: set-up -> b -> c
            for b in ranked(fed):
                for c in ranked(x for x in get(k, b, "canFeed") if delivers(x) and x != b):
                    patch = add_method(b)
                    second = add_method(c, None, roles_filled | set((patch or {}).get("setup.roles+", {}).get(b, [])))
                    if patch is None or second is None:
                        continue
                    patch = {"setup.methods+": patch["setup.methods+"] + second["setup.methods+"],
                             "setup.roles+": {**patch["setup.roles+"], **second["setup.roles+"]}}
                    if consistent(patch) is None:
                        continue
                    propose("combine", "extend_output", output,
                            f"Add {name(k, b)} then {name(k, c)} to deliver {name(k, output)}.",
                            "two more steps", {"methods": [ref(k, b), ref(k, c)], "output": ref(k, output)},
                            patch, "high", "blocking", standard=False)
                    kept += 1
                    break
                if kept == config.MAX_PER_KIND:
                    break

    covered_processes: set[str] = set()
    for key, found in issues.items():
        if found["code"] != "MISSING_ROLE" or found.get("accepted"):
            continue                              # left out on purpose: not proposed again
        role = found["subject"]
        kept = 0
        for candidate in ranked(m for m in k.facts if role in get(k, m, "fillsRole") and linked(m)):
            patch = add_method(candidate, role)
            if consistent(patch) is None:
                continue
            effort, how = coupling_effort(candidate)
            propose("combine", "fill_role", role,
                    f"Add {name(k, candidate)} as {name(k, role)}.", how,
                    {"method": ref(k, candidate), "role": ref(k, role)}, patch, effort, "high", standard=False)
            covered_processes |= set(get(k, candidate, "modelsProcess"))
            kept += 1
            if kept == config.MAX_PER_KIND:
                break
    for key, found in issues.items():
        if found["code"] != "MISSING_PRIMARY_PROCESS" or found["subject"] in covered_processes \
                or found.get("accepted"):
            continue
        process = found["subject"]
        kept = 0
        for candidate in ranked(m for m in k.facts if process in get(k, m, "modelsProcess") and linked(m)):
            patch = add_method(candidate)
            if consistent(patch) is None:
                continue
            effort, how = coupling_effort(candidate)
            propose("combine", "add_process", process,
                    f"Add {name(k, candidate)} to model {name(k, process)}.", how,
                    {"method": ref(k, candidate), "process": ref(k, process)}, patch, effort, "high",
                    standard=False)
            kept += 1
            if kept == config.MAX_PER_KIND:
                break

    def chain_patch(chain: dict) -> dict:
        chain_methods = list(dict.fromkeys(s["method"] for s in chain["steps"]))
        software = setup.software if setup.software in chain["software"] else None
        return {"setup": {"software": software, "methods": chain_methods, "roles": {},
                          "reference_chain": chain["id"]}}

    serving = {t["id"] for t in k.templates.values() if context.challenge in t["serves"]}
    for chain in k.chains.values():
        chain_methods = {s["method"] for s in chain["steps"]}
        if chain_methods & set(setup.left_out):
            continue                              # it would bring back a component left out on purpose
        if chain["template"] in serving and chain_methods & set(methods) and chain_methods != set(methods):
            same = bool(setup.software) and setup.software in chain["software"]
            propose("combine", "adopt_reference_chain", chain["id"],
                    f"Adopt the standard workflow {name(k, chain['id'])}: it contains "
                    f"{names(k, chain_methods & set(methods))}.",
                    " → ".join(name(k, m) for m in dict.fromkeys(s["method"] for s in chain["steps"])),
                    {"chain": ref(k, chain["id"]), "software": refs(k, chain["software"])},
                    chain_patch(chain), "low" if same else "medium", "high", standard=True)

    # ---- optional components: left out of the workflow at first, recommended here ---------
    chain = k.chains.get(setup.reference_chain) if setup.reference_chain else None
    best = before["best_template"]
    optional_roles: list[tuple[str, list[str], str | None]] = []   # (method or "", roles, software)
    if chain:
        for chain_step in chain["steps"]:
            m = chain_step["method"]
            if m in methods or m in setup.left_out:
                continue
            found_entry = next((o for o in optional_roles if o[0] == m), None)
            if found_entry:
                found_entry[1].append(chain_step["role"])
            else:
                optional_roles.append((m, [chain_step["role"]], chain_step["software"]))
    elif best:
        for slot in best["slots"]:
            role = slot["role"]["id"]
            if not slot["mandatory"] and not slot["filled_by"] and role not in {
                    r for held in setup.left_out.values() for r in held}:
                optional_roles.append(("", [role], None))
    has_processes = set().union(*(set(get(k, m, "modelsProcess")) for m in methods)) if methods else set()
    for m, held, software in optional_roles:
        candidates = [m] if m else ranked(
            x for x in k.facts if held[0] in get(k, x, "fillsRole") and linked(x)
            and (not scope or scope & set(get(k, x, "canBeImplementedIn"))))[:2]
        for candidate in candidates:
            patch = {"setup.methods+": [candidate], "setup.roles+": {candidate: list(held)}} if m \
                else add_method(candidate, held[0])
            if consistent(patch) is None:
                continue
            adds = set(get(k, candidate, "modelsProcess")) - has_processes
            in_software = software or next(iter(scope & set(get(k, candidate, "canBeImplementedIn"))), None)
            propose("combine", "add_component", held[0],
                    f"Optional component: add {name(k, candidate)} as {names(k, held)}"
                    + (f". It adds {names(k, adds)}." if adds else ". It refines a process already modelled."),
                    (f"part of the standard workflow {name(k, chain['id'])}" if chain else "optional slot of the usual workflow")
                    + "; its effect was neglected at first",
                    {"method": ref(k, candidate), "role": ref(k, held[0]), "roles": [ref(k, r) for r in held],
                     "adds_processes": refs(k, adds), "module": chains.module(k, in_software, candidate)},
                    patch, "low" if in_software else "medium", "medium", standard=bool(chain))
            proposals[-1]["keep"] = True

    if context.intent == "ImpactAnalysis" or context.scenario == "FutureScenario":
        expressed = set().union(*(k.output_variables.get(o, set()) for o in context.outputs))
        primary = k.primary.get(context.challenge, set())
        target = next((m for m in methods if expressed & set(get(k, m, "producesOutput"))), None) or max(
            methods, key=lambda m: len(set(get(k, m, "modelsProcess")) & primary))
        hard = [r for r in reqs if r["kind"] == "method" and r["strength"] == "hard" and r["on_property"]]
        passing = []
        for x in sorted(get(k, target, "isAlternativeTo"), key=lambda c: (not shares_software(c), name(k, c))):
            if x in methods or not set(roles[target]) <= set(get(k, x, "fillsRole")):
                continue
            S = {"methods": [x], "outs": set(), "in_hand": set(), "outputs": [], "driver": None, "map_ok": True}
            if all(judge_rule(k, r, S)[0] != "fail" for r in hard):
                passing.append(x)
        if len(passing) >= 2:
            propose("combine", "ensemble", target,
                    f"Run {name(k, passing[0])} and {name(k, passing[1])} alongside {name(k, target)}: "
                    "comparing several methods shows how much the result depends on the method.",
                    "ensemble of alternative methods for the same job",
                    {"methods": [ref(k, x) for x in passing[:2]], "role": [ref(k, r) for r in roles[target]]},
                    {}, "medium", "medium", advice=True, standard=False)

    # ---- effect of every action so far -------------------------------------------------
    def measure(action: dict) -> dict | None:
        after = before if not action["patch"] else diagnose(k, apply_patch(req, action["patch"]), reqs)
        gone = [key for key in issues if key not in {i["key"] for i in after["issues"]}]
        action["resolves"] = gone
        action["effect"] = {
            "fit_before": before["fit"]["score"], "fit_after": after["fit"]["score"],
            "label_after": after["fit"]["label"],
            "coverage_before": before["coverage"]["primary"], "coverage_after": after["coverage"]["primary"],
            "blocking_before": before["fit"]["blocking"], "blocking_after": after["fit"]["blocking"],
        }
        if action["advice"]:
            return action
        if action.get("keep"):                 # an optional component: shown even with no gain
            return action if after["fit"]["blocking"] <= before["fit"]["blocking"] else None
        if after["fit"]["score"] < before["fit"]["score"]:
            return None
        if after["fit"]["score"] == before["fit"]["score"] and not gone:
            return None
        gains = ["blocking" if issues[key]["severity"] == BLOCKING else issues[key]["gain_hint"] for key in gone]
        if gains:
            action["gain"] = min(gains, key=lambda g: GAIN_ORDER.get(g, 9))
        return action

    actions = [a for a in (measure(p) for p in proposals) if a]

    # ---- path D: replace ----------------------------------------------------------------
    resolved = {key for a in actions for key in a["resolves"]}
    stuck = [i for i in before["issues"] if i["severity"] == BLOCKING and i["key"] not in resolved]
    replacements: list[dict] = []
    for m in methods:
        found = []
        for x in get(k, m, "isAlternativeTo"):
            if x in methods or not set(roles[m]) <= set(get(k, x, "fillsRole")):
                continue
            patch = {"setup.methods-": [m], "setup.methods+": [x], "setup.roles+": {x: list(roles[m])}}
            after = diagnose(k, apply_patch(req, patch), reqs)
            better = after["fit"]["score"] - before["fit"]["score"]
            if better >= config.REPLACE_GAIN or (stuck and after["fit"]["blocking"] < before["fit"]["blocking"]):
                found.append((after["fit"]["score"], x, patch))
        for score, x, patch in sorted(found, key=lambda f: (-f[0], not shares_software(f[1]), f[1]))[:config.MAX_PER_KIND]:
            replacements.append({
                "path": "replace", "kind": "replace_method", "subject": m,
                "message": f"Replace {name(k, m)} with {name(k, x)} ({names(k, roles[m])}).",
                "detail": "same job, better fit for this study",
                "proposal": {"replace": ref(k, m), "by": ref(k, x)}, "patch": patch,
                "effort": "low" if shares_software(x) else "medium", "gain": "high", "advice": False,
                "standard_practice": None,
            })
    if stuck or before["fit"]["label"] == "poor fit":
        ranked_chains = []
        for chain in k.chains.values():
            template = k.templates.get(chain["template"], {})
            if context.challenge not in template.get("serves", set()):
                continue
            if context.outputs and not set(context.outputs) & template.get("delivers", set()):
                continue
            chain_methods = {s["method"] for s in chain["steps"]}
            if chain_methods == set(methods) or chain_methods & set(setup.left_out):
                continue                          # the same set-up, or one bringing back what was left out
            after = diagnose(k, apply_patch(req, chain_patch(chain)), reqs)
            ranked_chains.append((after["fit"]["score"], chain))
        for score, chain in sorted(ranked_chains, key=lambda c: (-c[0], c[1]["id"]))[:2]:
            replacements.append({
                "path": "replace", "kind": "replace_setup", "subject": chain["id"],
                "message": f"Switch to the standard workflow {name(k, chain['id'])}.",
                "detail": " → ".join(name(k, m) for m in dict.fromkeys(s["method"] for s in chain["steps"])),
                "proposal": {"chain": ref(k, chain["id"]), "software": refs(k, chain["software"])},
                "patch": chain_patch(chain), "effort": "high", "gain": "blocking", "advice": False,
                "standard_practice": True,
            })
    actions += [a for a in (measure(p) for p in replacements) if a]

    # ---- what each action is for, where it runs, what it brings ---------------------------
    data_rows: dict[str, dict] = {}
    for entry in before["data"]:
        data_rows.setdefault(entry["id"], entry)
    wanted_for = {v: o for o in context.outputs for v in k.output_variables.get(o, set())}
    # no output chosen: the variables behind the main outputs of the challenge still matter most
    usual_for = {} if context.outputs else {
        v: o for o in sorted(k.primary_outputs.get(context.challenge, set()))
        for v in k.output_variables.get(o, set())}

    def takes(method: str) -> set[str]:
        return set(get(k, method, "requiresMandatoryInput")) | set(get(k, method, "acceptsOptionalInput"))

    def target_of(action: dict) -> dict:
        """What is missing, that this action supplies: actions with the same target are alternatives."""
        kind, subject = action["kind"], action["subject"]
        if action["path"] in ("more_data", "finer_data") or kind == "feed_input":
            entry = data_rows.get(subject)
            use = "calibration" if kind == "add_calibration_data" else entry["kind"] if entry else "mandatory"
            return {"type": "data", **ref(k, subject), "use": use, "definition": None,
                    "nature": entry["nature"] if entry else chains.input_kind(k, subject)}
        if kind == "extend_output":
            return {"type": "output", **ref(k, subject), "definition": k.questions.get(subject)}
        if kind == "fill_role":
            return {"type": "role", **ref(k, subject), "definition": k.role_definitions.get(subject)}
        if kind == "add_component":
            return {"type": "component", **ref(k, subject), "definition": k.role_definitions.get(subject)}
        if kind == "add_process":
            return {"type": "process", **ref(k, subject), "definition": None}
        if kind in ("replace_method", "ensemble"):
            return {"type": "method", **ref(k, subject), "definition": names(k, roles[subject])}
        return {"type": "workflow", "id": "workflow", "label": "Standard workflow", "definition": None}

    def software_note(added: list[str], replaced: str | None, chain_software: set[str] | None) -> dict:
        """Where the proposed method(s) run, compared with the software of the set-up."""
        if chain_software is not None:
            own = set(chain_software)
        else:
            sets = [set(get(k, m, "canBeImplementedIn")) for m in added]
            own = set.intersection(*sets) or set().union(*sets)
        if setup.software:
            current = {setup.software}
        else:                                  # no software stated: the one(s) the set-up methods share
            rest = [m for m in methods if m != replaced] or [m for m in methods]
            current = set.intersection(*(set(get(k, m, "canBeImplementedIn")) for m in rest))
        shared = own & current
        if shared:
            return {"same": True, "software": refs(k, shared), "current": refs(k, current),
                    "text": "in the same software (" + names(k, shared) + ")"}
        if not own:
            return {"same": None, "software": [], "current": refs(k, current), "text": "no software recorded for it"}
        if not current:
            return {"same": None, "software": refs(k, own), "current": refs(k, current), "text": "available in " + names(k, own)}
        return {"same": False, "software": refs(k, own), "current": refs(k, current),
                "text": "in another software: " + names(k, own)
                + (" (you use " if setup.software else " (your methods run in ") + names(k, current) + ")"}

    def contribution(method: str, around: list[str], replaced: str | None, proposal: dict) -> dict:
        """The variables a proposed method computes, and what each one is used for."""
        gone = set(get(k, replaced, "producesOutput")) if replaced else set()
        variables = []
        for variable in get(k, method, "producesOutput"):
            users = [m for m in around if m != method and variable in takes(m)]
            # already computed by a method the set-up keeps: it brings nothing new
            already = [m for m in methods if m != replaced and variable in get(k, m, "producesOutput")]
            if already:
                variables.append({**ref(k, variable), "use": None, "new": False,
                                  "already_by": [ref(k, m) for m in already]})
                continue
            if variable in wanted_for:
                use = "expected output: " + name(k, wanted_for[variable])
            elif users:
                use = "input of " + names(k, users)
            elif variable in usual_for:
                use = "usual output: " + name(k, usual_for[variable])
            elif proposal.get("passes") and proposal["passes"]["id"] == variable:
                use = "stands for " + name(k, proposal["variable"]["id"]) + " of " + \
                    ", ".join(m["label"] or m["id"] for m in proposal["to"])
            else:
                use = None
            variables.append({**ref(k, variable), "use": use, "already_by": [],
                              "new": bool(replaced) and variable not in gone})
        variables.sort(key=lambda v: (v["use"] is None, (v["label"] or v["id"]).lower()))
        return {"method": ref(k, method), "variables": variables}

    for action in actions:
        patch = action["patch"]
        replaced = (patch.get("setup.methods-") or [None])[0]
        chain_software = None
        if "setup" in patch:
            added = [m for m in patch["setup"]["methods"] if m not in methods]
            chain_software = k.chains[patch["setup"]["reference_chain"]]["software"]
        elif action["kind"] == "ensemble":
            added = [m["id"] for m in action["proposal"]["methods"]]
        else:
            added = list(patch.get("setup.methods+", []))
        around = apply_patch(req, patch).setup.methods if patch else methods
        action["target"] = target_of(action)
        action["software"] = software_note(added, replaced, chain_software) \
            if added or chain_software is not None else None
        action["contributes"] = [contribution(m, around, replaced, action["proposal"]) for m in added[:4]]

    # ---- ranking, groups, limits ---------------------------------------------------------
    for action in actions:
        action["id"] = hashlib.sha1(
            f"{action['path']}|{action['kind']}|{action['subject']}|{sorted(action['proposal'].items(), key=str)}"
            .encode()).hexdigest()[:12]
    seen: set[str] = set()
    actions = [a for a in actions if not (a["id"] in seen or seen.add(a["id"]))]
    # two actions with the same patch are one action: keep the most specific kind
    specific = ["feed_input", "extend_output", "fill_role", "add_process"]
    actions.sort(key=lambda a: specific.index(a["kind"]) if a["kind"] in specific else 0)
    patches: set[str] = set()
    unique = []
    for action in actions:
        signature = repr(sorted(action["patch"].items(), key=str))
        if action["patch"] and signature in patches:
            continue
        patches.add(signature)
        unique.append(action)
    actions = unique
    actions.sort(key=lambda a: (
        GAIN_ORDER.get(a["gain"], 9), EFFORT_ORDER[a["effort"]],
        -(a["effect"]["fit_after"] - a["effect"]["fit_before"]),
        a["standard_practice"] is False, a["message"],
    ))
    groups: dict[str, int] = {}
    for action in actions:
        group = f"{action['kind']}:{action['subject']}"
        groups[group] = groups.get(group, 0) + 1
    for action in actions:
        group = f"{action['kind']}:{action['subject']}"
        action["exclusive_group"] = group if groups[group] > 1 else None
        action["group"] = "fix_first" if action["gain"] == "blocking" else \
            "recommended" if action["gain"] == "high" else "optional"
        if action["standard_practice"] is False and action["path"] == "combine":
            action["message"] += " Possible combination, not a standard practice."
    # at most a few actions of each kind, so that every kind of improvement stays visible
    shown: list[dict] = []
    per_kind: dict[str, int] = {}
    for action in actions:
        per_kind[action["kind"]] = per_kind.get(action["kind"], 0) + 1
        if per_kind[action["kind"]] <= config.MAX_PER_KIND and len(shown) < config.MAX_ACTIONS:
            shown.append(action)
    return {"diagnosis": before, "actions": shown, "more_available": len(actions) - len(shown),
            "components": components(k, req, reqs, before)}


def components(k, req: SetupRequest, reqs: list[dict], before: dict) -> list[dict]:
    """Each method of the set-up as a component that can be left out, with what is lost.

    In an integrated software (MIKE SHE, SWAT...) each process is a module that can be
    switched off. Switching one off is a modelling choice, not an error, but it has a
    price: processes no longer modelled, variables no longer computed, expected outputs
    no longer delivered, and downstream modules that lose an input and then need it as
    data (a boundary condition) instead.
    """
    setup = req.setup
    methods = list(dict.fromkeys(setup.methods))
    if len(methods) < 2:
        return []
    roles = assign_roles(k, setup)
    primary = k.primary.get(req.context.challenge, set())
    mandatory = {s["role"]["id"] for s in (before["best_template"] or {"slots": []})["slots"] if s["mandatory"]}
    keys_before = {i["key"] for i in before["issues"]}
    delivered_before = {o["id"] for o in before["outputs"] if o["status"] == "delivered"}
    produced_before = set().union(*(set(get(k, m, "producesOutput")) for m in methods))
    takes = lambda m: set(get(k, m, "requiresMandatoryInput")) | set(get(k, m, "acceptsOptionalInput"))

    # the software the methods live in: the one chosen, else the one(s) they all share
    scope = software_scope(k, setup)
    if not scope:
        shared = [set(get(k, m, "canBeImplementedIn")) for m in methods]
        scope = set.intersection(*shared) if shared else set()
    swapped: dict[str, list[dict]] = {}

    def swaps(m: str) -> list[dict]:
        """Other methods of the SAME software able to do exactly the job(s) of m, each one tried.

        An integrated software often offers several methods for one module (MIKE SHE:
        Richards, gravity flow or a two-layer budget for the unsaturated zone). Changing is
        a one-click choice; the fit after the change tells whether it suits the study.
        """
        if m in swapped:
            return swapped[m]
        held = set(roles[m])
        others = {r for o in methods if o != m for r in roles[o]}
        found_swaps = []
        where = set(scope)
        if not where & set(get(k, m, "canBeImplementedIn")):
            where |= set(get(k, m, "canBeImplementedIn"))   # e.g. a method added from another software
        candidates = {x for s in where for r in held for x in k.modules.get(s, {}).get(r, [])} - set(methods)
        # ... and the methods a standard workflow uses for this job next to the other methods of
        # the set-up, whatever their software (HEC-HMS hydrographs -> HEC-RAS 2D hydraulics)
        rest = set(methods) - {m}
        for chain in k.chains.values():
            if {s["method"] for s in chain["steps"]} & rest:
                candidates |= {s["method"] for s in chain["steps"] if s["role"] in held} - set(methods)
        for x in sorted(candidates):
            if not held <= set(get(k, x, "fillsRole")):
                continue
            fills = set(get(k, x, "fillsRole"))
            if k.separability.get(x) == "integrated":
                if fills != held and (fills - held) & others:
                    continue                      # a package: its other jobs are already done
                jobs = sorted(fills) if not (fills - held) & others else sorted(held)
            else:
                jobs = sorted(held)
            swap = {"setup.methods-": [m], "setup.methods+": [x], "setup.roles+": {x: jobs}}
            after = diagnose(k, apply_patch(req, swap), reqs)
            new = {i["key"] for i in after["issues"] if i["code"] in CONSISTENCY | {"OVERLAP"}} - keys_before
            if new:
                continue
            found_swaps.append({
                **ref(k, x), "roles": [ref(k, r) for r in jobs],
                "software": refs(k, (set(get(k, x, "canBeImplementedIn")) & where) or set(get(k, x, "canBeImplementedIn"))),
                "same_software": bool(set(get(k, x, "canBeImplementedIn")) & scope),
                # its module: in the set-up's software if it has one there, else where it is documented
                "module": next((chains.module(k, s, x) for s in
                                sorted(get(k, x, "canBeImplementedIn"), key=lambda s: (s not in where, s))
                                if (s, x) in k.module_info), None),
                "fit_after": after["fit"]["score"], "blocking_after": after["fit"]["blocking"],
                "outputs_lost": [o["label"] or o["id"] for o in after["outputs"]
                                 if o["id"] in delivered_before and o["status"] != "delivered"],
                "patch": swap,
            })
        found_swaps.sort(key=lambda x: (not x["same_software"], -x["fit_after"], (x["label"] or x["id"]).lower()))
        swapped[m] = found_swaps[:6]
        return swapped[m]

    found = []
    for m in methods:
        patch = {"setup.methods-": [m], "setup.left_out+": {m: list(roles[m])}}
        after = diagnose(k, apply_patch(req, patch), reqs)
        rest = [o for o in methods if o != m]
        processes_after = set().union(*(set(get(k, o, "modelsProcess")) for o in rest))
        produced_after = set().union(*(set(get(k, o, "producesOutput")) for o in rest))
        lost_processes = set(get(k, m, "modelsProcess")) - processes_after
        lost_variables = produced_before - produced_after
        rows_after = {d["id"]: d for d in after["data"] if d["kind"] == "mandatory"}
        # downstream: a method that received a variable from this one and now needs it as data
        downstream = []
        for other in rest:
            for variable in sorted((lost_variables & takes(other)) | {
                    i["variable"] for i in k.interfaces
                    if i["from"] in roles[m] and i["to"] in roles[other]
                    and i["variable"] in lost_variables and other in get(k, m, "canFeed")}):
                entry = rows_after.get(variable)
                required = variable in get(k, other, "requiresMandatoryInput")
                if entry is None and required:
                    continue                      # still computed inside the chain by another method
                downstream.append({
                    "method": ref(k, other), "variable": ref(k, variable), "required": required,
                    "nature": chains.input_kind(k, variable, other),
                    "then": entry["status"] if entry else "unused",
                })
        new_blocking = [i for i in after["issues"] if i["severity"] == BLOCKING and i["key"] not in keys_before]
        lost_outputs = [o for o in after["outputs"] if o["id"] in delivered_before and o["status"] != "delivered"]
        needed = bool(set(roles[m]) & mandatory)
        costly = bool(lost_outputs or new_blocking or (lost_processes & primary))
        found.append({
            **ref(k, m),
            "roles": [ref(k, r) for r in roles[m]],
            "needed": needed,                                  # a mandatory part of the usual workflow
            "verdict": "costly" if costly else "minor" if (lost_processes or downstream or needed) else "free",
            "loses": {
                "processes": [{**r, "main": r["id"] in primary} for r in refs(k, lost_processes)],
                "variables": refs(k, lost_variables),
                "outputs": [{"id": o["id"], "label": o["label"]} for o in lost_outputs],
                "downstream": downstream,
                "blocking": [i["message"] for i in new_blocking],
            },
            "effect": {"fit_before": before["fit"]["score"], "fit_after": after["fit"]["score"],
                       "blocking_after": after["fit"]["blocking"]},
            # other methods of the same software for the same job (a simpler module, for example)
            "same_software": [ref(k, x["id"]) for x in swaps(m)],
            "alternatives": swaps(m),
            "patch": patch,
        })
    return found


# ----------------------------------------------------------------------------
# Wizard options
# ----------------------------------------------------------------------------

def options(k, step: str, body: dict) -> dict:
    """Options of one step of the set-up wizard, each with a status and a reason.

    status: ok | needs_change | needs_combination | unavailable (only this one is greyed out).
    """
    setup = Setup(**(body.get("setup") or {}))
    context = body.get("context") or {}
    methods = [m for m in setup.methods if m in k.facts]
    roles = assign_roles(k, setup) if methods else {}
    roles_filled = {r for m in methods for r in roles[m]}
    procs = set().union(*(set(get(k, m, "modelsProcess")) for m in methods)) if methods else set()
    outs = set().union(*(set(get(k, m, "producesOutput")) for m in methods)) if methods else set()

    def option(item_id: str, status: str = "ok", reason: str | None = None, **extra) -> dict:
        return {**ref(k, item_id), "status": status, "reason": reason, **extra}

    if step == "software":
        found = []
        for software in sorted(k.software, key=lambda s: name(k, s).lower()):
            count = sum(1 for m in k.facts if software in get(k, m, "canBeImplementedIn"))
            if count:
                found.append(option(software, count=count, open=k.software[software]["open"],
                                    free=k.software[software]["free"]))
        return {"step": step, "options": found}

    if step == "methods":
        # grouped by role: "which method do you use for <role>?" A method able to do several
        # jobs appears once per job (Linear Reservoir: runoff transform AND baseflow).
        groups = []
        for role in role_order(k):
            members = sorted(
                (m for m in k.facts if role in get(k, m, "fillsRole")
                 and (not setup.software or setup.software in get(k, m, "canBeImplementedIn"))),
                key=lambda m: name(k, m).lower())
            if members:
                view = lambda m: next(v for v in chains.role_views(k, m) if v["id"] == role)
                groups.append({
                    "role": ref(k, role), "definition": k.role_definitions.get(role),
                    "options": [option(m, also=[ref(k, r) for r in get(k, m, "fillsRole") if r != role],
                                       receives=view(m)["receives"], delivers=view(m)["delivers"])
                                for m in members],
                })
        return {"step": step, "groups": groups}

    if step == "reference_chain":
        found = []
        for chain in k.chains.values():
            same = bool(setup.software) and setup.software in chain["software"]
            template = k.templates.get(chain["template"], {})
            # the workflow starts with its essential components; the optional ones are listed apart
            essential, optional = chains.essential_split(k, chain["steps"], chain["template"],
                                                         context.get("outputs") or [])
            found.append(option(chain["id"], same_software=same, software=refs(k, chain["software"]),
                                challenges=refs(k, template.get("serves", set())),
                                delivers=refs(k, chains.chain_delivers(k, chain["steps"], chain["template"])), note=chain["note"],
                                methods=[ref(k, m) for m in dict.fromkeys(s["method"] for s in essential)],
                                optional_methods=[ref(k, m) for m in dict.fromkeys(s["method"] for s in optional)]))
        found.sort(key=lambda o: (not o["same_software"], o["label"] or o["id"]))
        return {"step": step, "options": found}

    if step == "challenge":
        found = []
        for challenge in sorted(k.challenges, key=lambda c: name(k, c)):
            relevant = k.primary.get(challenge, set()) | k.secondary.get(challenge, set())
            if procs & relevant:
                found.append(option(challenge))
            elif any(challenge in t["serves"] and roles_filled & {s["role"] for s in t["slots"]}
                     for t in k.templates.values()):
                found.append(option(challenge, "needs_combination",
                                    "Your set-up covers none of its processes alone, but can be part of a workflow for it."))
            else:
                found.append(option(challenge, "unavailable", "Your set-up models none of the processes of this challenge."))
        return {"step": step, "options": found}

    if step == "objective":
        found = []
        S = {"methods": methods, "outs": outs, "in_hand": set(), "outputs": [], "driver": None, "map_ok": True}
        for objective in sorted(k.vocabulary["objective"], key=lambda o: name(k, o)):
            failed = None
            for requirement in requirements.ontology.requirements_of(objective):
                if requirement["kind"] == "method" and requirement["strength"] == "hard" \
                        and requirement["rule_id"] != "produces-expected-output" \
                        and judge_rule(k, requirement, S)[0] == "fail":
                    failed = requirement["rationale"] or requirement["label"]
                    break
            found.append(option(objective, "needs_change" if failed else "ok", failed))
        return {"step": step, "options": found}

    if step == "output":
        challenge = context.get("challenge")
        primary = k.primary_outputs.get(challenge, set())
        found = []
        for output in sorted(k.typical_outputs.get(challenge, set()), key=lambda o: (o not in primary, name(k, o))):
            expressed = k.output_variables.get(output, set())
            needs_map = "MapForm" in k.output_forms.get(output, set())
            map_ok = not needs_map or any(
                expressed & set(get(k, m, "producesOutput"))
                and ("FullyDistributed" in get(k, m, "hasSpatialRepresentation")
                     or set(get(k, m, "hasDimensionality")) & {"Dim2D", "Dim3D"}) for m in methods)
            extra = {"variables": refs(k, expressed), "suggested": output in primary,
                     "question": k.questions.get(output)}
            if expressed <= knowledge.closure(k, outs)[0] and map_ok:   # computed, or derived from what is computed
                found.append(option(output, **extra))
            elif any(output in t["delivers"] and roles_filled & {s["role"] for s in t["slots"]}
                     for t in k.templates.values()) or any(
                    expressed - outs <= set(get(k, b, "producesOutput"))
                    for m in methods for b in get(k, m, "canFeed")):
                found.append(option(output, "needs_combination",
                                    "Your set-up must be combined with another method to deliver it.", **extra))
            else:
                found.append(option(output, "unavailable", "Your set-up cannot lead to this output.", **extra))
        return {"step": step, "options": found}

    if step == "output_step":
        return {"step": step, "options": [option(s) for s in timesteps.order(k.hours, k.hours)]}

    if step in ("entity", "intent", "scenario"):
        return {"step": step, "options": [option(v) for v in sorted(k.vocabulary[step], key=lambda v: name(k, v))]}

    if step == "data":
        # the checklist: what the set-up needs from outside, with where it can come from
        req, _ = normalise(k, SetupRequest(setup=setup, context=Context(**context), data=body.get("data") or []))
        found = diagnose(k, req)["data"]
        return {"step": step, "options": found,
                "time_steps": [ref(k, s) for s in timesteps.order(k.hours, k.hours)]}

    raise SetupError([f"Unknown step: {step}"])
