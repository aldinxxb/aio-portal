"""Options of the problem-definition wizard steps: goal, driver, water entity, output.

The number next to each option answers one question:
"if I pick this, how many methods of my challenge are still possible?"
It is computed with the same requirement rules as the final ranking (rules.py),
so the wizard and the results can never disagree.

Each function returns a list of options:
    {"id", "label", "count", "reason", "hint", "suggested", "related"}
    reason     why the option cannot be chosen (None = it can be chosen)
    hint       a short sentence shown under the option (None = nothing)
    suggested  True for the options the ontology proposes first

Layering: preview.py -> ontology.py, rules.py  (never queries or GraphDB directly).
"""
from types import SimpleNamespace

from app import chains, knowledge, ontology, rules, timesteps


class Preview:
    """Tries out answers on top of a draft. Loads the methods and their facts only once."""

    def __init__(self, draft):
        self.draft = draft
        self.methods = ontology.list_methods(draft.challenge)
        self.facts = ontology.method_facts()

    def survivors(self, **changes) -> set[str]:
        """Ids of the methods no hard rule excludes, if the draft had these extra answers."""
        draft = self.draft
        problem = SimpleNamespace(
            challenge=draft.challenge,
            objective=draft.objective,
            intent=draft.intent,
            scenario=draft.scenario,
            entity=draft.entity,
            drivers=list(draft.drivers),
            outputs=list(draft.outputs),
            available_variables=list(draft.available_variables),
        )
        for field, value in changes.items():
            setattr(problem, field, value)
        judged = rules.judge_methods(problem, self.methods, self.facts)
        return {m["id"] for m in judged["methods"] if not m["excluded"]}


def option(item: dict, count: int, reason: str | None = None,
           hint: str | None = None, suggested: bool = False) -> dict:
    return {
        "id": item["id"],
        "label": item["label"],
        "count": count,
        "reason": reason,
        "hint": hint,
        "suggested": suggested,
        "related": [],      # other concepts tied to the option (outputs: their variables)
    }


def objective_options(draft) -> list[dict]:
    """Study goals. A goal with a hard rule (Forecasting -> continuous) removes methods."""
    preview = Preview(draft)
    found = []
    for goal in ontology.list_vocabulary("objective"):
        count = len(preview.survivors(objective=goal["id"]))
        reason = None if count else "No method of this challenge meets what this goal requires"
        found.append(option(goal, count, reason))
    return found


def driver_options(draft) -> list[dict]:
    """Key drivers of the challenge. The default driver is the one assumed if the user skips."""
    preview = Preview(draft)
    found = []
    for driver in ontology.list_drivers(draft.challenge):
        count = len(preview.survivors(drivers=[driver["id"]]))
        reason = None if count else "No method of this challenge can represent this driver"
        hint = "Assumed if you skip this step" if driver["default"] else None
        found.append(option(driver, count, reason, hint, suggested=driver["default"]))
    return found


def entity_options(draft) -> list[dict]:
    """Water entities. An entity counts the methods able to deliver an output that concerns it."""
    preview = Preview(draft)
    outputs = ontology.list_outputs(draft.challenge)
    methods_of_output = {o["id"]: preview.survivors(outputs=[o["id"]]) for o in outputs}

    found = []
    for entity in ontology.list_vocabulary("entity"):
        relevant = [o["id"] for o in outputs if entity["id"] in o["entities"]]
        methods: set[str] = set()
        for output_id in relevant:
            methods |= methods_of_output[output_id]
        if not relevant:
            reason = "No typical output of this challenge concerns this water entity"
        elif not methods:
            reason = "No method can deliver the outputs that concern this water entity"
        else:
            reason = None
        found.append(option(entity, len(methods), reason))
    return found


def output_options(draft) -> list[dict]:
    """Typical outputs of the challenge, primary ones first, with their plain question.

    If a water entity was chosen, the outputs that do not concern it cannot be picked.
    """
    preview = Preview(draft)
    found = []
    for output in ontology.list_outputs(draft.challenge):
        count = len(preview.survivors(outputs=[output["id"]]))
        if draft.entity and draft.entity not in output["entities"]:
            reason = "This output does not concern the water entity you chose"
        elif not count:
            reason = "With your answers so far, no method of this challenge can produce this output"
        else:
            reason = None
        chosen = option(output, count, reason, output["question"], output["primary"])
        chosen["related"] = ontology.output_variables(output["id"])   # e.g. hydrograph -> discharge
        found.append(chosen)
    return found


# ----------------------------------------------------------------------------
# Time-step steps (ontology 0.8.0): the count follows the aggregation rules
# ----------------------------------------------------------------------------

def step_options(draft, passes, reason: str, hint: str) -> list[dict]:
    """The four time-step classes, finest first, each with the methods that pass a rule."""
    k = knowledge.load()
    methods = [m["id"] for m in ontology.list_methods(draft.challenge)]
    found = []
    for step in timesteps.order(k.hours, k.hours):
        count = sum(1 for m in methods if passes(k, chains.get(k, m, "supportsTimeStep"), step))
        item = {"id": step, "label": k.labels.get(step)}
        found.append(option(item, count, None if count else reason, hint))
    return found


def timestep_options(draft) -> list[dict]:
    """Time step of the RESULTS (rule B): a method running finer also counts."""
    return step_options(
        draft,
        lambda k, supports, step: timesteps.can_deliver(k.hours, supports, step),
        "No method of this challenge runs this finely",
        "Counts the methods running at this step or finer",
    )


def datastep_options(draft) -> list[dict]:
    """Time step of the DATA of the user (rule A): methods that can use it without splitting it."""
    return step_options(
        draft,
        lambda k, supports, step: timesteps.usable_as_is(k.hours, supports, step),
        "Every method of this challenge needs finer data",
        "Counts the methods that can use data at this step as it is",
    )


# ----------------------------------------------------------------------------
# Process step: ordered by relevance to the challenge
# ----------------------------------------------------------------------------

def process_options(draft) -> list[dict]:
    """Processes of the challenge, the directly connected ones first.

    primary    the challenge is about this process (hasPrimaryProcess): highlighted
    secondary  it influences the challenge (hasSecondaryProcess)
    other      involved, but neither of the two
    Inside each group, the process with the most methods comes first.
    """
    k = knowledge.load()
    primary = k.primary.get(draft.challenge, set())
    secondary = k.secondary.get(draft.challenge, set())
    rank = lambda p: 0 if p in primary else 1 if p in secondary else 2
    hints = [
        "Directly connected to this challenge",
        "Influences this challenge",
        "Involved, less central",
    ]
    rows = ontology.option_counts("options_processes", challenge=draft.challenge)
    rows.sort(key=lambda r: (rank(r["id"]), -r["count"], r["label"] or r["id"]))
    found = []
    for row in rows:
        level = rank(row["id"])
        reason = None if row["count"] else "No method in the ontology models this process"
        found.append(option(row, row["count"], reason, hints[level], suggested=level == 0))
    return found
