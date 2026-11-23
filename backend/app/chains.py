"""Method combination: recommending CHAINS of methods rather than single methods.

A hydrological model is assembled from components: a loss method, a transform, a
baseflow method, a routing method... The ontology (0.8.0) describes this with
  * component roles      which job a method does (fillsRole)
  * role interfaces      which role may pass which variable to which role
  * chain templates      the roles a kind of study needs, in order
  * reference chains     curated, standard-practice combinations (HEC-HMS event flood, ...)
  * canFeed              method A can pass its output to method B (built by the ontology)
  * isAlternativeTo      two methods doing the same job (used to propose a replacement)

This file judges a chain for one user (evaluate), builds new chains from the
templates (generate) and puts the best ones first (recommend).

Layering: chains.py -> knowledge.py, timesteps.py  (never queries or GraphDB directly).
Every function takes 'k', the knowledge loaded by knowledge.load().
"""
from types import SimpleNamespace

from app import knowledge, timesteps

RUNNABLE = "runnable"
CHECK = "check"

GENERATED_NOTE = "Possible combination, not a standard practice."
MAX_TRIED = 4000          # generated chains: how many combinations are looked at
MAX_KEPT = 30             # ... and how many runnable ones are kept before stopping


def ref(k, item_id: str | None) -> dict | None:
    """An ontology id with its readable name."""
    return None if item_id is None else {"id": item_id, "label": k.labels.get(item_id)}


def refs(k, ids) -> list[dict]:
    return sorted((ref(k, i) for i in ids), key=lambda r: (r["label"] or r["id"]).lower())


def context(available=(), data_step=None, output_steps=(), licence=None, modes=(),
            software=None, obtainable=None, measured=None) -> SimpleNamespace:
    """What the user told us that matters for a chain.

    available     variables the user already has
    data_step     time step of the user's data (rule A)
    output_steps  time steps the user wants results at (ranking only)
    licence       None, "open" (open source only) or "free" (free of charge only)
    modes         required temporal modes, one set per hard requirement (e.g. [{"Continuous"}])
    software      the software the user works in: only workflows that use it are proposed
    obtainable    variables open data can give FOR THE STUDY AREA (None = the whole catalogue)
    measured      ... and among them, those measured (to calibrate against)
    """
    return SimpleNamespace(
        available=set(available), data_step=data_step, output_steps=list(output_steps),
        licence=licence, modes=[set(m) for m in modes], software=software,
        obtainable=obtainable, measured=measured,
    )


def can_get(k, ctx) -> set[str]:
    """Variables open data can give: for the study area if one was chosen, else anywhere."""
    return k.obtainable if getattr(ctx, "obtainable", None) is None else ctx.obtainable


def measured(k, ctx) -> set[str]:
    return k.measured if getattr(ctx, "measured", None) is None else ctx.measured


def get(k, method: str, prop: str) -> list[str]:
    return k.facts.get(method, {}).get(prop, [])


def derivations(k, variable: str) -> list[dict]:
    """The recorded ways of deriving a variable: from what, with which technique.

    Each input says how many open datasets provide it, so the user knows where to start.
    """
    return [
        {
            "from": [{**r, "datasets": len({s["dataset"] for s in k.data.get(r["id"], []) if s["dataset"]})}
                     for r in refs(k, d["inputs"])],
            "how": d["method"],
        }
        for d in k.derivations.get(variable, [])
    ]


# ----------------------------------------------------------------------------
# Kinds of input, and the different jobs of one method
# ----------------------------------------------------------------------------

FORCING = "forcing"            # time-varying input from outside the water system (rain, temperature)
BOUNDARY = "boundary"          # boundary condition: a flow or state entering the model at its limits
STATIC = "static"              # fixed description of the site (terrain, channel geometry, soil)
INITIAL = "initial"            # initial state (warm-up run or observed snapshot)

INPUT_KIND_TEXT = {
    FORCING: "forcing",
    BOUNDARY: "boundary condition",
    STATIC: "static description",
    INITIAL: "initial state",
}


def input_kind(k, variable: str, method: str | None = None) -> str:
    """Forcing, boundary condition, static description or initial state.

    The ontology has no class for this yet, so it is derived:
      * initial state        the method lists it under requiresInitialCondition
      * static description   a ParameterVariable (terrain model, channel geometry, ...)
      * boundary condition   a flow or state that some method computes: it enters the model
                             at its limits, from an upstream method or from a measurement
                             (discharge, water level, effective rainfall, recharge, ...)
      * forcing              any other time-varying input: it comes from outside the water
                             system (precipitation, temperature, radiation, ...)
    """
    if method and variable in get(k, method, "requiresInitialCondition"):
        return INITIAL
    if variable in k.static:
        return STATIC
    if variable in k.produced:
        return BOUNDARY
    return FORCING


def role_views(k, method: str) -> list[dict]:
    """One entry per job the method can do, with what it receives and gives IN THAT JOB.

    Linear Reservoir, for example, is two different things: as a runoff transform it
    turns effective rainfall into a hydrograph; as a baseflow method it turns recharge
    into the slow groundwater contribution. The role interfaces tell them apart.
    """
    takes = (set(get(k, method, "requiresMandatoryInput")) | set(get(k, method, "acceptsOptionalInput"))
             | set(get(k, method, "requiresInitialCondition")))
    gives = set(get(k, method, "producesOutput"))
    views = []
    for role in get(k, method, "fillsRole"):
        receives: set[str] = set()
        replaces: set[str] = set()
        for interface in k.interfaces:
            if interface["to"] == role:
                if interface["variable"] in takes:
                    receives.add(interface["variable"])
                elif interface["substitutes"] & takes:
                    receives.add(interface["variable"])
                    replaces |= interface["substitutes"] & takes
        delivers = {i["variable"] for i in k.interfaces if i["from"] == role and i["variable"] in gives}
        views.append({
            **ref(k, role),
            "definition": k.role_definitions.get(role),
            "receives": refs(k, receives),
            # what this job usually receives, whatever the method (shown when nothing is recorded)
            "usually_receives": refs(k, {i["variable"] for i in k.interfaces if i["to"] == role}),
            "replaces": refs(k, replaces),        # its own input that the received variable stands for
            "delivers": refs(k, delivers),
        })
    return views


def module(k, software: str | None, method: str) -> dict | None:
    """The method as implemented in a software: module name, time step, spatial resolution."""
    info = k.module_info.get((software, method)) if software else None
    if info is None:
        return None
    return {**info, "software": ref(k, software)}


def essential_split(k, steps: list[dict], template_id: str | None,
                    outputs=()) -> tuple[list[dict], list[dict]]:
    """Split the steps of a workflow into ESSENTIAL ones and OPTIONAL ones.

    A workflow first keeps only what the study cannot do without; the components whose
    effect can be neglected at first (interception, snow, a separate routing...) are kept
    aside and recommended as improvements. A method is essential when:
      * it fills a mandatory slot of the workflow's template (loss, transform...);
      * continuous water balance: it is the first of baseflow / groundwater flow (one is needed);
      * it computes a variable behind a chosen output that no essential method gives;
      * an essential method needs an input that only this method can give (no open data).
    A method holding an essential role keeps all its roles (a package is never sliced).
    """
    template = k.templates.get(template_id) if template_id else None
    if template is None:
        return list(steps), []
    mandatory = {s["role"] for s in template["slots"] if s["mandatory"]}
    present = [s["role"] for s in steps]
    if template_id == "Tpl_ContinuousWaterBalance":
        for role in present:
            if role in ("Role_Baseflow", "Role_GroundwaterFlow"):
                mandatory.add(role)
                break
    essential = {s["method"] for s in steps if s["role"] in mandatory}
    wanted = set()
    for output in outputs:
        wanted |= k.output_variables.get(output, set())
    for _ in range(len(steps)):
        produced = set()
        for m in essential:
            produced |= set(get(k, m, "producesOutput"))
        reach = knowledge.closure(k, produced)[0]
        # inputs of essential methods with no usable data: no dataset FINE ENOUGH for the method
        # (rule C) and no derivation; only another method of the workflow can give them
        needed = set()
        for m in essential:
            others = set()                     # what the OTHER essential methods give (a method does not feed itself)
            for o in essential - {m}:
                others |= set(get(k, o, "producesOutput"))
            for v in set(get(k, m, "requiresMandatoryInput")) - set(get(k, m, "requiresInitialCondition")):
                if v in knowledge.closure(k, others)[0] or v in k.derived_from:
                    continue
                supports = get(k, m, "supportsTimeStep")
                if not any(source["dataset"] and timesteps.dataset_ok(k.hours, source["step"], supports)
                           for source in k.data.get(v, [])):
                    needed.add(v)
        lacking = (wanted - reach) | needed
        promote = [s["method"] for s in steps if s["method"] not in essential
                   and set(get(k, s["method"], "producesOutput")) & lacking]
        if not promote:
            break
        essential.add(promote[0])
    return [s for s in steps if s["method"] in essential], [s for s in steps if s["method"] not in essential]


def chain_delivers(k, steps: list[dict], template_id: str | None) -> set[str]:
    """The outputs of the template that THESE steps really deliver: every variable computed
    (or derived from what is computed) and, for a map, computed by a gridded method."""
    template = k.templates.get(template_id) if template_id else None
    if template is None:
        return set()
    methods = list(dict.fromkeys(s["method"] for s in steps))
    produced = set()
    for m in methods:
        produced |= set(get(k, m, "producesOutput"))
    reach = knowledge.closure(k, produced)[0]
    found = set()
    for output in template["delivers"]:
        variables = k.output_variables.get(output, set())
        if not variables <= reach:
            continue
        if "MapForm" in k.output_forms.get(output, set()) and not any(
                variables & set(get(k, m, "producesOutput")) and (
                    "FullyDistributed" in get(k, m, "hasSpatialRepresentation")
                    or set(get(k, m, "hasDimensionality")) & {"Dim2D", "Dim3D"}) for m in methods):
            continue
        found.add(output)
    return found


def optional_view(k, optional: list[dict], essential: list[dict]) -> list[dict]:
    """The optional components of a workflow, each with what it would add."""
    has_processes = set()
    has_variables = set()
    for s in essential:
        has_processes |= set(get(k, s["method"], "modelsProcess"))
        has_variables |= set(get(k, s["method"], "producesOutput"))
    found = []
    for method in dict.fromkeys(s["method"] for s in optional):
        held = [s for s in optional if s["method"] == method]
        software = held[0].get("software")
        found.append({
            "method": ref(k, method),
            "roles": [ref(k, s["role"]) for s in held],
            "software": ref(k, software),
            "module": module(k, software, method),
            "adds_processes": refs(k, set(get(k, method, "modelsProcess")) - has_processes),
            "adds_variables": refs(k, set(get(k, method, "producesOutput")) - has_variables),
        })
    return found


# ----------------------------------------------------------------------------
# Judging one chain
# ----------------------------------------------------------------------------

def evaluate(k, steps: list[dict], ctx: SimpleNamespace, challenge: str | None = None,
             covers: set[str] | None = None, coupling: str | None = None) -> dict:
    """Judge a chain for one user.

    steps: [{"method", "role", "software"}] from upstream to downstream. A method that
    fills several roles appears once per role.
    Returns the facts the user needs: status, reasons, the data to bring, conflicts...
    """
    hours = k.hours
    methods = list(dict.fromkeys(s["method"] for s in steps))       # each method once, in order
    roles_of = {m: [s["role"] for s in steps if s["method"] == m] for m in methods}

    # 1. what the chain produces by itself
    produced: set[str] = set()
    for m in methods:
        produced |= set(get(k, m, "producesOutput"))

    # 2. what each method receives through an interface (possibly replacing one of its inputs)
    received: dict[str, set[str]] = {m: set() for m in methods}
    conflicts: list[dict] = []
    for interface in k.interfaces:
        givers = [m for m in methods if interface["from"] in roles_of[m]
                  and interface["variable"] in get(k, m, "producesOutput")]
        takers = [m for m in methods if interface["to"] in roles_of[m]]
        for giver in givers:
            for taker in takers:
                if giver == taker:
                    continue
                received[taker] |= {interface["variable"]} | interface["substitutes"]
                # 8. pairwise time-step check (rule D); never one common step for the whole chain
                if not timesteps.step_ok(hours, get(k, giver, "supportsTimeStep"),
                                         get(k, taker, "supportsTimeStep")):
                    conflict = {"from": giver, "to": taker}
                    if conflict not in conflicts:
                        conflicts.append(conflict)

    # 3-4. per method: inputs that come from inside the chain, and those the user must bring
    internal: dict[str, set[str]] = {}
    external: dict[str, set[str]] = {}
    for m in methods:
        mandatory = set(get(k, m, "requiresMandatoryInput"))
        initial = set(get(k, m, "requiresInitialCondition"))     # warm-up run: never "missing"
        # computed by ANOTHER step (a method does not feed itself), or received through an interface
        by_others = set()
        for other in methods:
            if other != m:
                by_others |= set(get(k, other, "producesOutput"))
        internal[m] = {v for v in mandatory if v in by_others or v in received[m]}
        external[m] = mandatory - internal[m] - initial

    inputs = set().union(*external.values()) if external else set()
    parameters = set()
    for m in methods:
        parameters |= set(get(k, m, "hasPhysicalParameter"))
    parameters -= inputs
    initial_conditions = set()
    for m in methods:
        initial_conditions |= set(get(k, m, "requiresInitialCondition"))

    # 5-6. where each external variable can come from
    def state(variable: str) -> str:
        if variable in ctx.available:
            return "have"
        return "open_data" if variable in can_get(k, ctx) else "missing"

    missing = sorted(v for v in inputs | parameters if state(v) == "missing")

    # 7. calibration: is there measured data to calibrate against?
    calibrated = [m for m in methods if get(k, m, "hasCalibrationParameter")]
    targets = set()
    for m in calibrated:
        targets |= set(get(k, m, "isCalibratedAgainst"))
    calibration_ok = not calibrated or bool(targets & (measured(k, ctx) | ctx.available))

    # 9. temporal mode shared by the steps (steady-state methods are neutral)
    shared_modes: set[str] | None = None
    for m in methods:
        modes = set(get(k, m, "hasTemporalMode")) - {"SteadyState"}
        if modes:
            shared_modes = modes if shared_modes is None else shared_modes & modes
    shared_modes = shared_modes or set()
    has_modes = any(set(get(k, m, "hasTemporalMode")) - {"SteadyState"} for m in methods)
    # an offline chain may run a continuous model, extract events and feed an event model
    mode_ok = bool(shared_modes) or not has_modes or coupling == "OfflineOneWay"

    # 10. how much of the challenge's primary processes the chain covers
    if covers is None:
        covers = set()
        for m in methods:
            covers |= set(get(k, m, "modelsProcess"))
    primary = k.primary.get(challenge, set()) if challenge else set()
    coverage = round(len(covers & primary) / len(primary), 3) if primary else None

    # 11. software and licences
    software = list(dict.fromkeys(s["software"] for s in steps if s.get("software")))
    all_open = bool(software) and all(k.software.get(s, {}).get("open") for s in software)
    all_free = bool(software) and all(k.software.get(s, {}).get("free") for s in software)

    # ---- the user's own constraints ---------------------------------------------
    # rule A: the methods that take the user's (or a dataset's) forcing must accept its time step
    too_coarse = [
        m for m in methods
        if ctx.data_step and external[m]
        and not timesteps.usable_as_is(hours, get(k, m, "supportsTimeStep"), ctx.data_step)
    ]
    # temporal mode demanded by a hard requirement (e.g. forecasting -> continuous)
    wrong_mode = [sorted(allowed) for allowed in ctx.modes
                  if has_modes and coupling != "OfflineOneWay" and not (shared_modes & allowed)]

    # 12. verdict and its reasons, in plain words
    reasons: list[str] = []
    if missing:
        reasons.append("No data source for: " + ", ".join(k.labels.get(v, v) for v in missing) + ".")
    if not calibration_ok:
        reasons.append("No measured data to calibrate against ("
                       + ", ".join(k.labels.get(v, v) for v in sorted(targets)) + ").")
    for conflict in conflicts:
        reasons.append(
            f"{k.labels.get(conflict['from'], conflict['from'])} cannot run as finely as "
            f"{k.labels.get(conflict['to'], conflict['to'])} needs."
        )
    if not mode_ok:
        reasons.append("The steps share no temporal mode (event-based vs continuous).")
    for m in too_coarse:
        reasons.append(f"{k.labels.get(m, m)} needs data at a finer time step than yours.")
    for allowed in wrong_mode:
        reasons.append("Your goal requires a " + " or ".join(
            k.labels.get(a, a) for a in allowed) + " simulation.")

    problem_methods = set(too_coarse) | {c["from"] for c in conflicts}
    for m in methods:
        if any(state(v) == "missing" for v in external[m] | set(get(k, m, "hasPhysicalParameter"))):
            problem_methods.add(m)

    return {
        "status": RUNNABLE if not reasons else CHECK,
        "reasons": reasons,
        "methods": methods,
        "roles_of": roles_of,
        "internal": internal,
        "external": external,
        "inputs": [{**ref(k, v), "kind": "input", "state": state(v)} for v in sorted(inputs)],
        "parameters": [{**ref(k, v), "kind": "parameter", "state": state(v)} for v in sorted(parameters)],
        "initial_conditions": refs(k, initial_conditions),
        "missing": missing,
        "calibration": {"needed": bool(calibrated), "ok": calibration_ok, "against": refs(k, targets)},
        "conflicts": conflicts,
        "too_coarse": too_coarse,
        "problem_methods": problem_methods,
        "modes": sorted(shared_modes),
        "produced": produced,
        "covers": covers,
        "coverage": coverage,
        "software": software,
        "all_open": all_open,
        "all_free": all_free,
        "calibration_parameters": sum(len(get(k, m, "hasCalibrationParameter")) for m in methods),
    }


# ----------------------------------------------------------------------------
# Replacing a step that does not work (substitution)
# ----------------------------------------------------------------------------

def alternatives(k, method: str, roles: list[str], software: str | None,
                 ctx: SimpleNamespace, limit: int = 3) -> list[dict]:
    """Methods doing the same job that would not have the problem (same roles, data step ok,
    all inputs obtainable). The ones available in the same software come first."""
    found = []
    for other in get(k, method, "isAlternativeTo"):
        if not set(roles) <= set(get(k, other, "fillsRole")):
            continue
        if ctx.data_step and not timesteps.usable_as_is(
                k.hours, get(k, other, "supportsTimeStep"), ctx.data_step):
            continue
        needs = set(get(k, other, "requiresMandatoryInput")) | set(get(k, other, "hasPhysicalParameter"))
        needs -= set(get(k, other, "requiresInitialCondition"))
        # an input another step may produce is not held against the method
        unknown = [v for v in needs if v not in can_get(k, ctx) and v not in ctx.available
                   and not any(v in get(k, m, "producesOutput") for m in get(k, method, "isAlternativeTo") + [method])
                   and not any(v == i["variable"] or v in i["substitutes"] for i in k.interfaces)]
        if unknown:
            continue
        same = bool(software) and software in get(k, other, "canBeImplementedIn")
        found.append({**ref(k, other), "same_software": same})
    found.sort(key=lambda a: (not a["same_software"], (a["label"] or a["id"]).lower()))
    return found[:limit]


# ----------------------------------------------------------------------------
# Presenting a chain (what the portal shows)
# ----------------------------------------------------------------------------

def method_detail(k, method: str, verdict: dict | None, ctx: SimpleNamespace) -> dict:
    """What appears when a step is opened: inputs, parameters, outputs of the method."""
    def state(variable: str) -> str:
        if verdict is not None and variable in verdict["internal"].get(method, set()):
            return "internal"                       # produced by another step of the chain
        if variable in ctx.available:
            return "have"
        return "open_data" if variable in can_get(k, ctx) else "missing"

    def listed(prop: str, with_state: bool = False) -> list[dict]:
        items = refs(k, get(k, method, prop))
        return [{**i, "state": state(i["id"])} for i in items] if with_state else items

    initial = set(get(k, method, "requiresInitialCondition"))
    mandatory = [i for i in listed("requiresMandatoryInput", True) if i["id"] not in initial]
    return {
        "mandatory_inputs": mandatory,
        "optional_inputs": listed("acceptsOptionalInput"),
        "initial_conditions": listed("requiresInitialCondition"),
        "physical_parameters": listed("hasPhysicalParameter", True),
        "calibration_parameters": listed("hasCalibrationParameter"),
        "outputs": listed("producesOutput"),
        "supports_time_steps": [ref(k, s) for s in timesteps.order(k.hours, get(k, method, "supportsTimeStep"))],
        "typical_time_steps": [ref(k, s) for s in timesteps.order(k.hours, get(k, method, "hasTypicalTimeStep"))],
        "temporal_modes": listed("hasTemporalMode"),
        "software": listed("canBeImplementedIn"),
    }


def present(k, chain: dict, verdict: dict, ctx: SimpleNamespace) -> dict:
    """One chain as the portal shows it. chain: {id, label, kind, template, coupling, note, steps}."""
    software_of = {}
    for step in chain["steps"]:
        software_of.setdefault(step["method"], step.get("software"))

    steps = []
    for order, method in enumerate(verdict["methods"], start=1):
        roles = verdict["roles_of"][method]
        issue = None
        if method in verdict["too_coarse"]:
            issue = timesteps.DISAGGREGATION_WARNING
        elif any(c["from"] == method for c in verdict["conflicts"]):
            issue = "This method cannot run as finely as the next step needs."
        elif method in verdict["problem_methods"]:
            issue = "Some of its inputs have no data source."
        steps.append({
            "order": order,
            "method": ref(k, method),
            "roles": [ref(k, r) for r in roles],
            "software": ref(k, software_of.get(method)),
            "issue": issue,
            "alternatives": alternatives(k, method, roles, software_of.get(method), ctx) if issue else [],
            "detail": method_detail(k, method, verdict, ctx),
            "module": module(k, software_of.get(method), method),
            "essential": True,
        })

    template = k.templates.get(chain.get("template"), {})
    return {
        "id": chain["id"],
        "label": chain.get("label") or k.labels.get(chain["id"]) or chain["id"],
        "kind": chain["kind"],                                   # "reference" or "generated"
        "note": chain.get("note"),
        "template": ref(k, chain.get("template")),
        # what THIS workflow delivers over all its steps (a 1D river model: levels, not a flood map)
        "delivers": refs(k, chain_delivers(k, chain["steps"] + chain.get("optional_raw", []), chain.get("template"))),
        "coupling": ref(k, chain.get("coupling")),
        "status": verdict["status"],
        "reasons": verdict["reasons"],
        "score": chain.get("score"),
        "coverage": verdict["coverage"],
        "covers": refs(k, verdict["covers"]),
        "software": [
            {**ref(k, s), "open": k.software.get(s, {}).get("open", False),
             "free": k.software.get(s, {}).get("free", False)}
            for s in verdict["software"]
        ],
        "all_open": verdict["all_open"],
        "all_free": verdict["all_free"],
        "steps": steps,
        # components left out of the workflow at first (their effect can be neglected),
        # recommended as improvements: what each one would add
        "optional_steps": chain.get("optional_view", []),
        # each input with its nature: forcing, boundary condition or static description
        "inputs": [{**i, "nature": input_kind(k, i["id"])} for i in verdict["inputs"] + verdict["parameters"]],
        "initial_conditions": verdict["initial_conditions"],
        "calibration": verdict["calibration"],
        "temporal_modes": [ref(k, m) for m in verdict["modes"]],
    }


# ----------------------------------------------------------------------------
# Building new chains from a template
# ----------------------------------------------------------------------------

def connected(k, method: str, others: list[str]) -> bool:
    """Is the method linked by canFeed (either way) to one of the methods already chosen?"""
    return not others or any(
        method in get(k, other, "canFeed") or other in get(k, method, "canFeed") for other in others
    )


def pick_software(k, methods: list[str]) -> tuple[dict[str, str | None], str]:
    """Software for each method: one common software if it exists, otherwise each its first."""
    common = None
    for m in methods:
        available = set(get(k, m, "canBeImplementedIn"))
        common = available if common is None else common & available
    if common:
        # an open-source software first, then alphabetical
        chosen = sorted(common, key=lambda s: (not k.software.get(s, {}).get("open"), s))[0]
        return {m: chosen for m in methods}, "InternalCoupling"
    return {m: (sorted(get(k, m, "canBeImplementedIn")) or [None])[0] for m in methods}, "OfflineOneWay"


def generate(k, template_id: str, ctx: SimpleNamespace, challenge: str | None,
             known: list[frozenset]) -> list[dict]:
    """Chains built by walking the mandatory slots of a template, one method per role.

    A method filling several roles of the template occupies all of them. Each new method
    must be linked by canFeed to one already chosen. Only chains that evaluate as
    runnable are kept, and never one that is already a reference chain ('known').
    """
    template = k.templates[template_id]
    slot_roles = [s["role"] for s in template["slots"]]
    needed = [s["role"] for s in template["slots"] if s["mandatory"]]
    # continuous water balance: one of baseflow / groundwater flow must also be filled
    either = ["Role_Baseflow", "Role_GroundwaterFlow"] if template_id == "Tpl_ContinuousWaterBalance" else []
    fillers = {
        role: sorted(m for m in k.facts if role in get(k, m, "fillsRole")
                     and (not ctx.software or ctx.software in get(k, m, "canBeImplementedIn")))
        for role in set(slot_roles)
    }
    found: list[dict] = []
    seen: set[frozenset] = set(known)
    tried = 0

    def finish(assigned: dict[str, str]) -> None:
        nonlocal tried
        tried += 1
        methods = list(dict.fromkeys(assigned[r] for r in slot_roles if r in assigned))
        key = frozenset(methods)
        if key in seen:
            return
        seen.add(key)
        software, coupling = pick_software(k, methods)
        steps = [{"method": assigned[r], "role": r, "software": software[assigned[r]]}
                 for r in slot_roles if r in assigned]
        verdict = evaluate(k, steps, ctx, challenge, coupling=coupling)
        if verdict["status"] == RUNNABLE and passes_licence(verdict, ctx):
            found.append({
                "id": "GEN_" + "_".join(methods),
                "label": " → ".join(k.labels.get(m, m) for m in methods),
                "kind": "generated", "note": GENERATED_NOTE,
                "template": template_id, "coupling": coupling, "steps": steps, "verdict": verdict,
            })

    def walk(todo: list[str], assigned: dict[str, str]) -> None:
        if tried >= MAX_TRIED or len(found) >= MAX_KEPT:
            return
        todo = [r for r in todo if r not in assigned]
        if not todo:
            if either and not any(r in assigned for r in either):
                for role in either:
                    for method in fillers.get(role, []):
                        extra = place(method, assigned, role)
                        if extra is not None:
                            finish(extra)
            else:
                finish(assigned)
            return
        role = todo[0]
        for method in fillers.get(role, []):
            placed = place(method, assigned, role)
            if placed is not None:
                walk(todo[1:], placed)

    def place(method: str, assigned: dict[str, str], role: str | None = None) -> dict[str, str] | None:
        """Put the method in the chain; None if it would overlap what is already there.

        A package (aio:hasInseparableRoles true: GR4J, Richards...) takes every template
        role it fills, and all of them must be free. A method used for one job at a time
        (Linear Reservoir, the 2D solvers) takes only the role being filled.
        """
        chosen = list(dict.fromkeys(assigned.values()))
        if method not in chosen and not connected(k, method, chosen):
            return None
        placed = dict(assigned)
        one_job = role is not None and k.separability.get(method) == "separable"
        for slot_role in ([role] if one_job else slot_roles):
            if slot_role in get(k, method, "fillsRole"):
                if placed.get(slot_role, method) != method:
                    return None
                placed[slot_role] = method
        return placed

    walk(needed, {})
    return found


# ----------------------------------------------------------------------------
# Recommending chains for a challenge
# ----------------------------------------------------------------------------

def passes_licence(verdict: dict, ctx: SimpleNamespace) -> bool:
    if ctx.licence == "open":
        return verdict["all_open"]
    if ctx.licence == "free":
        return verdict["all_free"]
    return True


def step_match(k, verdict: dict, ctx: SimpleNamespace) -> float:
    """Share of the methods whose TYPICAL time step is the one the user works at (ranking only)."""
    wanted = set(ctx.output_steps) or ({ctx.data_step} if ctx.data_step else set())
    if not wanted:
        return 0.0
    methods = verdict["methods"]
    hits = sum(1 for m in methods if wanted & set(get(k, m, "hasTypicalTimeStep")))
    return hits / len(methods) if methods else 0.0


def recommend(k, challenge: str, outputs: list[str], ctx: SimpleNamespace,
              generated: int = 3) -> dict:
    """The chains to propose for a challenge, the best first.

    1. templates serving the challenge (and delivering the chosen outputs);
    2. their reference chains, each judged for this user;
    3. hard filters (licence); time step and temporal mode problems are shown as reasons,
       with a replacement method when one exists;
    4. a few generated chains, always labelled as non-standard and always after the
       runnable reference chains.
    """
    serving = [t for t in k.templates.values() if challenge in t["serves"]]
    note = None
    templates = serving
    if outputs:
        every = [t for t in serving if set(outputs) <= t["delivers"]]
        some = [t for t in serving if set(outputs) & t["delivers"]]
        if every:
            templates = every
        elif some:
            templates = some
            note = "No single workflow delivers all the outputs you chose: these deliver some of them."
        else:
            note = "No workflow of this challenge delivers the outputs you chose: showing all workflows."

    def delivers(template: dict, produced: set[str], methods: list[str] | None = None) -> bool:
        """Does the chain compute every variable behind the chosen outputs its template delivers?

        A map (MapForm) also needs a gridded method among those computing its variables:
        a 1D river model gives water levels, not a flood-extent map.
        """
        wanted = [o for o in outputs if o in template["delivers"]]
        reach = knowledge.closure(k, produced)[0]     # computed, or derived from what is computed
        for output in wanted:
            variables = k.output_variables.get(output, set())
            if not variables <= reach:
                return False
            if methods is not None and "MapForm" in k.output_forms.get(output, set()):
                if not any(variables & set(get(k, m, "producesOutput")) and (
                        "FullyDistributed" in get(k, m, "hasSpatialRepresentation")
                        or set(get(k, m, "hasDimensionality")) & {"Dim2D", "Dim3D"}) for m in methods):
                    return False
        return True

    candidates: list[dict] = []
    for template in templates:
        for chain in k.chains.values():
            if chain["template"] != template["id"]:
                continue
            if ctx.software and ctx.software not in chain["software"]:
                continue                              # not a workflow of the user's software
            # the workflow is judged on its ESSENTIAL steps; the others are recommended aside
            essential, optional = essential_split(k, chain["steps"], chain["template"], outputs)
            verdict = evaluate(k, essential, ctx, challenge, None, chain["coupling"])
            if not passes_licence(verdict, ctx) or not delivers(template, verdict["produced"], verdict["methods"]):
                continue
            candidates.append({**chain, "steps": essential, "kind": "reference", "label": k.labels.get(chain["id"]),
                               "verdict": verdict, "optional_view": optional_view(k, optional, essential),
                               "optional_raw": optional})

    known = [frozenset(c["verdict"]["methods"]) for c in candidates]
    if generated:
        for template in templates:
            built = [c for c in generate(k, template["id"], ctx, challenge, known)
                     if delivers(template, c["verdict"]["produced"], c["verdict"]["methods"])]
            candidates += built

    # ranking score (weights from the specification; tune later)
    most = max((c["verdict"]["calibration_parameters"] for c in candidates), default=0) or 1
    for c in candidates:
        v = c["verdict"]
        licence = 1.0 if v["all_open"] else 0.5 if v["all_free"] else 0.0
        c["score"] = round(
            0.40 * (v["coverage"] or 0.0)
            + 0.20 * (c["kind"] == "reference")
            + 0.15 * (v["status"] == RUNNABLE)
            + 0.10 * step_match(k, v, ctx)
            + 0.10 * licence
            - 0.05 * v["calibration_parameters"] / most,
            3,
        )

    # runnable first; a generated chain never comes before a runnable reference chain
    candidates.sort(key=lambda c: (c["verdict"]["status"] != RUNNABLE, c["kind"] != "reference",
                                   -c["score"], c["id"]))
    reference = [c for c in candidates if c["kind"] == "reference"]
    extra = [c for c in candidates if c["kind"] == "generated"][:generated]
    shown = sorted(reference + extra, key=lambda c: candidates.index(c))

    return {
        "challenge": ref(k, challenge),
        "note": note,
        "templates": [
            {**ref(k, t["id"]), "definition": t["definition"], "delivers": refs(k, t["delivers"]),
             "slots": [{"role": ref(k, s["role"]), "mandatory": s["mandatory"]} for s in t["slots"]]}
            for t in templates
        ],
        "chains": [present(k, c, c["verdict"], ctx) for c in shown],
    }


# ----------------------------------------------------------------------------
# One method: what it can be combined with (Modeling Approach entry)
# ----------------------------------------------------------------------------

def combine(k, method: str, software: str | None, available: set[str]) -> dict:
    """Around one method: who feeds it, whom it feeds, what could replace it, the standard
    chains that use it, and where each of its inputs can come from (your data, open data
    fine enough for the method, or another method)."""
    roles = get(k, method, "fillsRole")

    def neighbour(other: str) -> dict:
        shared = sorted(set(get(k, other, "canBeImplementedIn")) & set(get(k, method, "canBeImplementedIn")))
        return {
            **ref(k, other),
            "roles": [ref(k, r) for r in get(k, other, "fillsRole")],
            "same_software": bool(software) and software in get(k, other, "canBeImplementedIn"),
            "shared_software": [ref(k, s) for s in shared],
        }

    def by_software(items: list[dict]) -> list[dict]:
        return sorted(items, key=lambda n: (not n["same_software"], (n["label"] or n["id"]).lower()))

    feeds = by_software([neighbour(o) for o in get(k, method, "canFeed")])
    fed_by = by_software([neighbour(o) for o in k.facts if method in get(k, o, "canFeed")])
    alike = by_software([neighbour(o) for o in get(k, method, "isAlternativeTo")])

    used_in = []
    for chain in k.chains.values():
        methods = list(dict.fromkeys(s["method"] for s in chain["steps"]))
        if method in methods:
            used_in.append({
                **ref(k, chain["id"]),
                "methods": [ref(k, m) for m in methods],
                "software": [ref(k, s) for s in sorted(chain["software"])],
                "same_software": bool(software) and software in chain["software"],
                "template": ref(k, chain["template"]),
            })
    used_in.sort(key=lambda c: (not c["same_software"], c["label"] or c["id"]))

    supports = get(k, method, "supportsTimeStep")
    initial = set(get(k, method, "requiresInitialCondition"))

    def source(variable: str, kind: str) -> dict:
        """Where one input can come from."""
        datasets: dict[str, dict] = {}
        for found in k.data.get(variable, []):
            if not found["dataset"]:
                continue
            entry = datasets.setdefault(found["dataset"], {**ref(k, found["dataset"]),
                                                           "steps": [], "fine_enough": False})
            if found["step"] and found["step"] not in [s["id"] for s in entry["steps"]]:
                entry["steps"].append(ref(k, found["step"]))
            # rule C: is this dataset fine enough for the method?
            if timesteps.dataset_ok(k.hours, found["step"], supports):
                entry["fine_enough"] = True
        producers = [n for n in fed_by if variable in get(k, n["id"], "producesOutput")]
        return {
            **ref(k, variable),
            "kind": kind,                                   # mandatory, optional, parameter, initial
            "have": variable in available,
            "datasets": sorted(datasets.values(),
                               key=lambda d: (not d["fine_enough"], d["label"] or d["id"])),
            "derived_from": refs(k, k.derived_from.get(variable, set())),
            "producers": by_software(producers),
        }

    inputs = (
        [source(v, "mandatory") for v in sorted(set(get(k, method, "requiresMandatoryInput")) - initial)]
        + [source(v, "optional") for v in sorted(get(k, method, "acceptsOptionalInput"))]
        + [source(v, "parameter") for v in sorted(get(k, method, "hasPhysicalParameter"))]
        + [source(v, "initial") for v in sorted(initial)]
    )

    # the method alone: can each mandatory input come from the user, from open data that is
    # fine enough (rule C), or from a derivation? If not, another method must provide it.
    reasons = []
    for item in inputs:
        if item["kind"] != "mandatory" or item["have"] or item["derived_from"]:
            continue
        if any(d["fine_enough"] for d in item["datasets"]):
            continue
        name = item["label"] or item["id"]
        why = "open data exists but is too coarse" if item["datasets"] else "no open data"
        if item["producers"]:
            reasons.append(f"{name}: {why}; another method must provide it "
                           f"(for example {item['producers'][0]['label'] or item['producers'][0]['id']}).")
        else:
            reasons.append(f"{name}: {why}.")
    alone = {"status": RUNNABLE if not reasons else CHECK, "reasons": reasons}

    return {
        **ref(k, method),
        "roles": [ref(k, r) for r in roles],
        "complete_model": len(roles) >= 4,                  # e.g. GR4J: a full model by itself
        "supports_time_steps": [ref(k, s) for s in timesteps.order(k.hours, supports)],
        "typical_time_steps": [ref(k, s) for s in timesteps.order(k.hours, get(k, method, "hasTypicalTimeStep"))],
        "alone": alone,
        "fed_by": fed_by,
        "feeds": feeds,
        "alternatives": alike,
        "chains": used_in,
        "inputs": inputs,
    }
