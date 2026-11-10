"""Collects the requirements that a URR implies.

A requirement is a rule the ontology attaches to a problem-definition value:
choosing 'Forecasting' adds 'continuous simulation required', and so on.
This file asks the ontology for each chosen value and merges the answers.

Layering: requirements.py -> ontology.py  (never queries or GraphDB directly).
"""
from app import ontology


def chosen_values(urr) -> list[str]:
    """Every problem-definition value the user picked, plus the challenge itself.

    Challenges such as ClimateChange carry requirements of their own, and when the
    user skips the driver step, the challenge's default driver is assumed so that
    driver-based rules still apply.
    """
    values = [urr.challenge]
    for single in (urr.objective, urr.intent, urr.scenario):
        if single:
            values.append(single)
    values += list(urr.drivers)
    values += list(urr.outputs)

    if not urr.drivers:
        for driver in ontology.list_drivers(urr.challenge):
            if driver["default"]:
                values.append(driver["id"])
    return values


def effective_drivers(urr) -> list[str]:
    """The drivers the rules should work with: the user's, or the default one."""
    if urr.drivers:
        return list(urr.drivers)
    return [d["id"] for d in ontology.list_drivers(urr.challenge) if d["default"]]


def collect(urr) -> list[dict]:
    """All requirements implied by the URR, merged, each with the values that caused it."""
    merged: dict[str, dict] = {}
    for value in chosen_values(urr):
        for req in ontology.requirements_of(value):
            entry = merged.setdefault(req["id"], {**req, "because": []})
            if value not in entry["because"]:
                entry["because"].append(value)

    # hard rules first, then soft (heaviest first), then the rest
    order = {"hard": 0, "soft": 1, "none": 2}
    return sorted(merged.values(), key=lambda r: (order[r["strength"]], -r["weight"], r["id"]))