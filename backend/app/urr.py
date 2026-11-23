from pydantic import BaseModel, Field

from app import knowledge, ontology, problem


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
    data_time_step: str | None = None                              # time step of the user's data


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

    # names the ontology has replaced (Catchement -> Catchment) are accepted and translated
    if urr.entity:
        urr.entity = ontology.replacements().get(urr.entity, urr.entity)

    problems += problem.check(urr)  # goal, intent, scenario, entity, drivers, outputs

    known_steps = knowledge.load().hours
    for step in ([urr.data_time_step] if urr.data_time_step else []) + list(urr.time_steps):
        if step not in known_steps:
            problems.append(f"Unknown time step: {step}")

    if urr.processes:
        processes = {"values": urr.processes, "source": "stated"}
    elif urr.outputs and (from_outputs := processes_for_outputs(urr.challenge, urr.outputs, challenge_processes)):
        # no process chosen, but outputs are: the processes the workflows delivering them model,
        # so that methods are not penalised for processes the outputs do not need
        processes = {"values": from_outputs, "source": "outputs"}
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
            "data_time_step": urr.data_time_step,
            **problem.echo(urr),
        },
    }


def processes_for_outputs(challenge: str, outputs: list[str], challenge_processes: list[str]) -> list[str]:
    """Processes of the challenge modelled by the standard workflows that deliver the outputs."""
    k = knowledge.load()
    found: set[str] = set()
    for chain in k.chains.values():
        template = k.templates.get(chain["template"], {})
        if challenge in template.get("serves", set()) and set(outputs) & template.get("delivers", set()):
            found |= chain["covers"]
    if not found:                                       # no workflow: the methods computing the variables
        wanted = set().union(*(k.output_variables.get(o, set()) for o in outputs))
        for facts in k.facts.values():
            if wanted & set(facts.get("producesOutput", [])):
                found |= set(facts.get("modelsProcess", []))
    return [p for p in challenge_processes if p in found]


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
    data_time_step: str | None = None


class ChainRequest(URR):
    """A URR plus the software licence the user accepts (None, "open" or "free") and,
    optionally, the software they work in (only its workflows are then proposed)."""

    licence: str | None = None
    software: str | None = None


class CombineRequest(BaseModel):
    """Around one method: the data the user has and the software they work in."""

    available_variables: list[str] = Field(default_factory=list)
    software: str | None = None


class CheckRequest(BaseModel):
    """The data the user says they have, to check against one method."""

    available_variables: list[str] = Field(default_factory=list)


class DatasetRequest(BaseModel):
    """The variables the user would like open data for."""

    variables: list[str] = Field(default_factory=list)


class WorkflowRequest(URR):
    """A URR plus, optionally, the methods to focus the workflow on."""

    methods: list[str] = Field(default_factory=list)