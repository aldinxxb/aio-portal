"""Everything the chain layer needs from the ontology, loaded in a handful of queries.

The chain logic (chains.py) compares many methods with each other; asking GraphDB one
question per comparison would be slow. So this file reads the relevant part of the
ontology once and keeps it as plain Python dictionaries for a short time.

Layering: knowledge.py -> ontology.py  (never queries or GraphDB directly).
"""
import threading
import time
from types import SimpleNamespace

from app import ontology, sparql_client

KEEP_SECONDS = 300         # after this the ontology is read again (it may have been reloaded)
_kept = {"at": 0.0, "value": None}
_building = threading.Lock()

# data obtained by measuring (needed to calibrate a method)
MEASURED = {"Observed", "RemoteSensingRetrieval"}


def first(values: dict, prop: str):
    found = values.get(prop, [])
    return found[0] if found else None


def is_true(values: dict, prop: str) -> bool:
    return first(values, prop) == "true"


def load(force: bool = False) -> SimpleNamespace:
    """The knowledge, read again from the ontology every few minutes.

    Nobody waits for the re-reading: when the knowledge is old, the caller gets the
    one in memory at once and a background thread reads the new one. Only the very
    first call (or force=True, after reloading the ontology) reads it on the spot.
    """
    if force or _kept["value"] is None:
        with _building:
            if force or _kept["value"] is None:
                if force:
                    sparql_client.clear_cache()
                    ontology.forget_requirements()
                _kept["value"] = build()
                _kept["at"] = time.time()
    elif time.time() - _kept["at"] > KEEP_SECONDS and _building.acquire(blocking=False):
        threading.Thread(target=_refresh, daemon=True).start()
    return _kept["value"]


def _refresh() -> None:
    """Read the knowledge again (called in the background, with _building held)."""
    try:
        _kept["value"] = build()
    except Exception:                      # GraphDB unreachable: keep what we have, try later
        pass
    finally:
        _kept["at"] = time.time()
        _building.release()


def build() -> SimpleNamespace:
    k = SimpleNamespace()
    k.labels = ontology.all_labels()
    k.facts = ontology.method_facts()                      # {method: {property: [values]}}

    # ---- time steps: {id: lower bound in hours} --------------------------------
    k.hours = {
        step: float(first(values, "minStepHours"))
        for step, values in ontology.describe("TimeStepClass").items()
        if first(values, "minStepHours") is not None
    }

    # ---- software licences ------------------------------------------------------
    k.software = {
        software: {"open": is_true(values, "isOpenSource"), "free": is_true(values, "isFreeOfCharge")}
        for software, values in ontology.describe("SoftwarePlatform").items()
    }

    # ---- roles and the flows allowed between them -------------------------------
    k.roles = list(ontology.describe("ComponentRole"))
    k.interfaces = [
        {
            "id": interface,
            "from": first(values, "fromRole"),
            "to": first(values, "toRole"),
            "variable": first(values, "exchangesVariable"),
            "substitutes": set(values.get("substitutesInput", [])),
            "coupling": first(values, "hasTypicalCoupling"),
            "spatial_match": is_true(values, "requiresMatchingSpatialRepresentation"),
        }
        for interface, values in ontology.describe("RoleInterface").items()
    ]

    # ---- chain templates (which roles, in which order) --------------------------
    slots = ontology.describe("ChainSlot")
    k.templates = {}
    for template, values in ontology.describe("ChainTemplate").items():
        k.templates[template] = {
            "id": template,
            "serves": set(values.get("servesChallenge", [])),
            "delivers": set(values.get("deliversOutput", [])),
            "definition": first(values, "definition"),
            "slots": sorted(
                (
                    {
                        "role": first(slots[s], "slotRole"),
                        "order": int(first(slots[s], "slotOrder") or 0),
                        "mandatory": is_true(slots[s], "isMandatorySlot"),
                    }
                    for s in values.get("hasSlot", []) if s in slots
                ),
                key=lambda slot: slot["order"],
            ),
        }

    # ---- reference chains (curated, standard-practice combinations) -------------
    steps = ontology.describe("ChainStep")
    k.chains = {}
    for chain, values in ontology.describe("ReferenceChain").items():
        k.chains[chain] = {
            "id": chain,
            "template": first(values, "instantiatesTemplate"),
            "coupling": first(values, "hasCouplingType"),
            "note": first(values, "note"),
            "covers": set(values.get("coversProcess", [])),
            "software": set(values.get("chainUsesSoftware", [])),
            "steps": sorted(
                (
                    {
                        "order": int(first(steps[s], "stepOrder") or 0),
                        "method": first(steps[s], "usesMethod"),
                        "role": first(steps[s], "stepRole"),
                        "software": first(steps[s], "stepSoftware"),
                    }
                    for s in values.get("hasStep", []) if s in steps
                ),
                key=lambda step: step["order"],
            ),
        }

    # ---- challenges and outputs -------------------------------------------------
    k.primary = ontology.pairs("hasPrimaryProcess")        # {challenge: {process}}
    k.secondary = ontology.pairs("hasSecondaryProcess")
    k.involves = ontology.pairs("involvesProcess")
    k.output_variables = ontology.pairs("isExpressedBy")   # {output: {variable}}
    k.output_forms = ontology.pairs("hasOutputForm")       # {output: {MapForm, ...}}
    k.typical_outputs = ontology.pairs("hasTypicalOutput") # {challenge: {output}}
    k.primary_outputs = ontology.pairs("hasPrimaryOutput")
    k.driver_variables = ontology.pairs("isCharacterizedBy")
    k.default_driver = ontology.pairs("hasDefaultDriver")
    k.questions = ontology.plain_questions()               # {output: the question it answers}
    k.definitions = {                                      # outputs and their forms, in one sentence
        item: first(values, "definition")
        for kind in ("ExpectedOutput", "OutputForm")
        for item, values in ontology.describe(kind).items()
    }
    k.role_definitions = {
        role: first(values, "definition")
        for role, values in ontology.describe("ComponentRole").items()
    }

    # ---- the values a request may name (used to refuse unknown names) -------------
    k.challenges = {c["id"] for c in ontology.list_challenges()}
    k.vocabulary = {
        kind: {v["id"] for v in ontology.list_vocabulary(kind)}
        for kind in ontology.VOCABULARIES
    }
    k.replaced = ontology.replacements()                   # deprecated name -> new name

    # ---- nature of the variables --------------------------------------------------
    kinds = ontology.variable_kinds()                      # {variable: {FluxVariable, ...}}
    k.static = {v for v, found in kinds.items() if "ParameterVariable" in found}
    k.states = {v for v, found in kinds.items() if "StateVariable" in found}
    k.produced = set()                                     # computed by at least one method
    for values in k.facts.values():
        k.produced |= set(values.get("producesOutput", []))

    # ---- open data: what exists for each variable -------------------------------
    k.data = ontology.data_by_variable()                   # {variable: [{dataset, provenance, step}]}
    k.measured = {
        variable for variable, sources in k.data.items()
        if any(source["provenance"] in MEASURED for source in sources)
    }

    # obtainable = has a dataset, or can be derived from obtainable variables
    recorded = ontology.describe("Derivation")
    derivations = [
        (first(values, "derivesVariable"), set(values.get("requiresDerivationInput", [])))
        for values in recorded.values()
    ]
    # every way of deriving a variable, with the technique: {variable: [{"inputs", "method"}]}
    k.derivations = {}
    for values in recorded.values():
        variable, inputs = first(values, "derivesVariable"), set(values.get("requiresDerivationInput", []))
        if variable and inputs:
            k.derivations.setdefault(variable, []).append(
                {"inputs": inputs, "method": first(values, "derivationMethod"),
                 # an exact post-processing of model results (aio:validForModelResults), or a
                 # way of obtaining data that needs more information (a rating curve...)
                 "model": is_true(values, "validForModelResults")})
    # the page of each dataset, to point the user to it
    k.dataset_urls = {d["id"]: d["url"] for d in ontology.list_datasets()}
    k.derived_from = {}                                    # {variable: the inputs it is derived from}
    k.obtainable = set(k.data)
    changed = True
    while changed:                                         # fixed point
        changed = False
        for variable, inputs in derivations:
            if variable and variable not in k.obtainable and inputs and inputs <= k.obtainable:
                k.obtainable.add(variable)
                k.derived_from[variable] = inputs
                changed = True

    # ---- software modules: a method as implemented in one software, with its usual
    #      time step and spatial resolution there (aio:SoftwareModule)
    k.module_info = {}                                     # {(software, method): {...}}
    for node, values in ontology.describe("SoftwareModule").items():
        software, method = first(values, "moduleOf"), first(values, "implementsMethod")
        if software and method:
            k.module_info[(software, method)] = {
                "id": node,
                "name": first(values, "moduleName"),
                "time_step": first(values, "moduleTimeStep"),
                "time_step_classes": values.get("moduleTimeStepClass", []),
                "spatial_unit": first(values, "moduleSpatialUnit"),
                "resolution": first(values, "moduleResolution"),
                "software": software,
            }

    # ---- integrated software: modules, and how a method may be used -----------------
    # A software is a set of MODULES: one per job (role), each with the methods that the
    # software offers for it. MIKE SHE, for example: evapotranspiration, interception,
    # snow, unsaturated zone, overland flow, saturated zone, river.
    k.modules = {}                                         # {software: {role: [methods]}}
    for method, values in k.facts.items():
        for software in values.get("canBeImplementedIn", []):
            for role in values.get("fillsRole", []):
                k.modules.setdefault(software, {}).setdefault(role, []).append(method)

    # The jobs a method is KNOWN to do on its own: the role sets it has in the standard
    # chains. GR4J always holds its four jobs together; Linear Reservoir is used as
    # baseflow alone; the 2D shallow water equations as hydraulics alone.
    k.uses = {}                                            # {method: {frozenset(roles)}}
    k.chain_pairs = set()                                  # two methods used together in a standard chain
    for chain in k.chains.values():
        held: dict[str, set[str]] = {}
        for step in chain["steps"]:
            held.setdefault(step["method"], set()).add(step["role"])
        for method, roles in held.items():
            k.uses.setdefault(method, set()).add(frozenset(roles))
        for a in held:
            for b in held:
                if a != b:
                    k.chain_pairs.add(frozenset((a, b)))

    # A method with several jobs is either a package or used for one job at a time:
    #   integrated  its jobs are one calculation (GR4J): added with all of them, or not at all
    #   separable   used for one job or another (Linear Reservoir): may hold a single job
    #
    # The ontology states it: aio:hasInseparableRoles true / false. Only when a method has
    # no statement is it inferred from the standard chains, as before:
    #   a chain uses it for part of its jobs  -> separable
    #   every chain uses all its jobs         -> integrated
    #   no chain uses it                      -> unknown (never sliced, never flagged)
    k.separability = {}
    k.separability_source = {}                             # "stated" in the ontology, or "inferred"
    for method, values in k.facts.items():
        fills = frozenset(values.get("fillsRole", []))
        uses = k.uses.get(method, set())
        stated = first(values, "hasInseparableRoles")
        k.separability_source[method] = "stated" if stated is not None else "inferred"
        if len(fills) <= 1:
            k.separability[method] = "separable"
        elif stated is not None:
            k.separability[method] = "integrated" if stated == "true" else "separable"
        elif any(use < fills for use in uses):
            k.separability[method] = "separable"
        elif uses:
            k.separability[method] = "integrated"
        else:
            k.separability[method] = "unknown"
    return k


def closure(k, produced: set[str]) -> tuple[set[str], dict[str, dict]]:
    """Everything that can be obtained from what a set-up computes.

    A variable is reachable if a method computes it, or if a derivation VALID FOR MODEL
    RESULTS gives it from reachable variables (runoff volume = time integral of discharge).
    Derivations meant for data (water level from discharge with a rating curve) do not
    count: they need information a model does not have. Returns the reachable variables
    and, for each derived one, the derivation used.
    """
    reach = set(produced)
    via: dict[str, dict] = {}
    changed = True
    while changed:
        changed = False
        for variable, ways in k.derivations.items():
            if variable in reach:
                continue
            for way in ways:
                if way["model"] and way["inputs"] <= reach:
                    reach.add(variable)
                    via[variable] = way
                    changed = True
                    break
    return reach, via
