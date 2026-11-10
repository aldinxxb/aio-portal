"""Checks the 'problem definition' part of a URR: goal, intent, scenario, entity,
drivers and expected outputs.

Layering: this file only talks to ontology.py (never to queries or GraphDB).
It receives the URR as a plain object, so it does not import urr.py (no circle).
"""
from app import ontology

# URR field -> vocabulary kind (single-value fields)
SINGLE_FIELDS = {
    "objective": "objective",
    "intent": "intent",
    "scenario": "scenario",
    "entity": "entity",
}
# URR field -> vocabulary kind (list fields)
LIST_FIELDS = {
    "drivers": "driver",
    "outputs": "output",
}


def check(urr) -> list[str]:
    """Return a list of problems (empty list = everything is fine)."""
    problems: list[str] = []

    for field, kind in SINGLE_FIELDS.items():
        value = getattr(urr, field, None)
        if value is None:
            continue
        known = {v["id"] for v in ontology.list_vocabulary(kind)}
        if value not in known:
            problems.append(f"Unknown {field}: {value}")

    for field, kind in LIST_FIELDS.items():
        values = getattr(urr, field, [])
        if not values:
            continue
        known = {v["id"] for v in ontology.list_vocabulary(kind)}
        for value in values:
            if value not in known:
                problems.append(f"Unknown {field[:-1]}: {value}")

    return problems


def echo(urr) -> dict:
    """The problem-definition fields exactly as they go back to the caller."""
    return {
        "objective": getattr(urr, "objective", None),
        "intent": getattr(urr, "intent", None),
        "scenario": getattr(urr, "scenario", None),
        "entity": getattr(urr, "entity", None),
        "drivers": list(getattr(urr, "drivers", [])),
        "outputs": list(getattr(urr, "outputs", [])),
    }