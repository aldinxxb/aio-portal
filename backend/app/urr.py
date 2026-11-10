from pydantic import BaseModel, Field

from app import ontology, problem  # NEW: problem


class URR(BaseModel):
    """User Requirement Representation: what the user told us, in a fixed shape."""

    challenge: str                                                 # required
    processes: list[str] = Field(default_factory=list)             # optional
    available_variables: list[str] = Field(default_factory=list)   # optional
    scales: list[str] = Field(default_factory=list)                # optional filter
    time_steps: list[str] = Field(default_factory=list)            # optional filter
    # NEW: the problem definition (all optional)
    objective: str | None = None                                   # e.g. Forecasting
    intent: str | None = None                                      # e.g. Prediction
    scenario: str | None = None                                    # e.g. CurrentScenario
    entity: str | None = None                                      # e.g. River
    drivers: list[str] = Field(default_factory=list)               # e.g. Rainfall
    outputs: list[str] = Field(default_factory=list)               # e.g. Hydrograph


def validate(urr: URR) -> dict:
    """Check a URR against the ontology and complete what the user left out."""
    problems: list[str] = []

    challenge_ids = {c["id"] for c in ontology.list_challenges()}
    if urr.challenge not in challenge_ids:
        # Without a valid challenge nothing else can be checked.
        return {"valid": False, "problems": [f"Unknown challenge: {urr.challenge}"]}

    challenge_processes = [p["id"] for p in ontology.list_processes(urr.challenge)]
    for process in urr.processes:
        if process not in challenge_processes:
            problems.append(f"Process {process} is not involved in {urr.challenge}")

    known_variables = {v["id"] for v in ontology.list_variables()}
    for variable in urr.available_variables:
        if variable not in known_variables:
            problems.append(f"Unknown variable: {variable}")

    problems += problem.check(urr)  # NEW: goal, intent, scenario, entity, drivers, outputs

    if urr.processes:
        processes = {"values": urr.processes, "source": "stated"}
    else:
        processes = {"values": challenge_processes, "source": "derived"}

    return {
        "valid": not problems,
        "problems": problems,
        "urr": {
            "challenge": urr.challenge,
            "processes": processes,
            "available_variables": urr.available_variables,
            "scales": urr.scales,
            "time_steps": urr.time_steps,
            **problem.echo(urr),  # NEW
        },
    }


class Draft(BaseModel):
    """A URR under construction: every field optional, filled in step by step."""

    challenge: str | None = None
    processes: list[str] = Field(default_factory=list)
    available_variables: list[str] = Field(default_factory=list)
    scales: list[str] = Field(default_factory=list)             # optional filter
    time_steps: list[str] = Field(default_factory=list)         # optional filter
    software: str | None = None
    methods: list[str] = Field(default_factory=list)
    # NEW: the problem definition, filled by the new wizard steps
    objective: str | None = None
    intent: str | None = None
    scenario: str | None = None
    entity: str | None = None
    drivers: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)


class CheckRequest(BaseModel):
    """The data the user says they have, to check against one method."""

    available_variables: list[str] = Field(default_factory=list)


class DatasetRequest(BaseModel):
    """The variables the user would like open data for."""

    variables: list[str] = Field(default_factory=list)


class WorkflowRequest(URR):
    """A URR plus, optionally, the methods to focus the workflow on."""

    methods: list[str] = Field(default_factory=list)