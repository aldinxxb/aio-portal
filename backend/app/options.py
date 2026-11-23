from app import ontology, preview, problem
from app.urr import Draft

# One entry per wizard step: what must be answered before it, and where its options
# come from. Two kinds of step:
#   "query"   -> a counting query lists the options; "empty_reason" says why an option
#                with no methods is greyed out;
#   "builder" -> a function of preview.py lists them (problem-definition steps: the
#                count is the number of methods left after the requirement rules).
STEPS = {
    "challenge": {
        "query": "options_challenges",
        "needs": [],
        "empty_reason": "No method in the ontology models the processes of this challenge",
    },
    "process": {"builder": preview.process_options, "needs": ["challenge"]},
        "variable": {
        "query": "options_variables",
        "needs": ["challenge"],
        "empty_reason": "No method of this challenge uses this variable",
    },
        "scale": {
        "query": "options_scales",
        "needs": ["challenge"],
        "empty_reason": "No method of this challenge works at this scale",
    },
    "timestep": {"builder": preview.timestep_options, "needs": ["challenge"]},
    "datastep": {"builder": preview.datastep_options, "needs": ["challenge"]},
        "software": {
        "query": "options_software",
        "needs": [],
        "empty_reason": "No method in the ontology can be implemented in this software",
    },
    "method": {
        "query": "options_methods_of_software",
        "needs": ["software"],
        "empty_reason": "The ontology records no process for this method",
    },
        "data": {
        "query": "options_data",
        "needs": [],
        "empty_reason": "No method requires this variable",
    },
    "objective": {"builder": preview.objective_options, "needs": ["challenge"]},
    "driver": {"builder": preview.driver_options, "needs": ["challenge"]},
    "entity": {"builder": preview.entity_options, "needs": ["challenge"]},
    "output": {"builder": preview.output_options, "needs": ["challenge"]},
}


class StepError(Exception):
    """A step cannot be answered. status_code tells the web layer which HTTP error to send."""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


def get_options(step: str, draft: Draft) -> dict:
    """List the options of one wizard step, filtered by the answers already given."""
    if step not in STEPS:
        raise StepError(f"Unknown step: {step}", 404)
    spec = STEPS[step]

    answers = {}
    for need in spec["needs"]:
        value = getattr(draft, need)
        if not value:
            raise StepError(f"Step '{step}' needs '{need}' to be answered first", 422)
        answers[need] = value

    if "challenge" in answers:
        known = {c["id"] for c in ontology.list_challenges()}
        if answers["challenge"] not in known:
            raise StepError(f"Unknown challenge: {answers['challenge']}", 422)

    if "builder" in spec:
        # the answers already given (goal, entity, ...) take part in the rules: check them
        problems = problem.check(draft)
        if problems:
            raise StepError("; ".join(problems), 422)
        found = spec["builder"](draft)
        return {
            "step": step,
            "options": [{**o, "enabled": o["reason"] is None} for o in found],
        }

    rows = ontology.option_counts(spec["query"], **answers)
    return {
        "step": step,
        "options": [
            {
                "id": r["id"],
                "label": r["label"],
                "count": r["count"],
                "enabled": r["count"] > 0,
                "reason": None if r["count"] > 0 else spec["empty_reason"],
                "hint": None,
                "suggested": False,
                "related": [],
            }
            for r in rows
        ],
    }