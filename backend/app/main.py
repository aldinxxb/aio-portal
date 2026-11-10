from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app import engine, ontology, options, urr, requirements, rules
from app.urr import URR, validate
from app.config import CORS_ORIGINS

app = FastAPI(title="AIO Portal API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_challenge(challenge_id: str) -> None:
    """Stop with a 404 error if the challenge is not in the ontology."""
    known = {c["id"] for c in ontology.list_challenges()}
    if challenge_id not in known:
        raise HTTPException(status_code=404, detail=f"Unknown challenge: {challenge_id}")
def reject_unknown_variables(variables: list[str]) -> None:
    """Stop with a 422 error if one of the variables is not in the ontology."""
    known = {v["id"] for v in ontology.list_variables()}
    unknown = [v for v in variables if v not in known]
    if unknown:
        raise HTTPException(status_code=422, detail=[f"Unknown variable: {v}" for v in unknown])

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/challenges")
def list_challenges():
    return ontology.list_challenges()


@app.get("/variables")
def list_variables():
    return ontology.list_variables()


@app.get("/challenges/{challenge_id}/processes")
def processes_of_challenge(challenge_id: str):
    require_challenge(challenge_id)
    return ontology.list_processes(challenge_id)


@app.get("/challenges/{challenge_id}/methods")
def methods_for_challenge(challenge_id: str):
    require_challenge(challenge_id)
    return ontology.list_methods(challenge_id)

@app.get("/methods/{method_id}")
def get_method(method_id: str):
    try:
        profile = ontology.method_profile(method_id)
    except ValueError:  # name with forbidden characters
        profile = None
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Unknown method: {method_id}")
    return profile
@app.post("/methods/{method_id}/check")
def check_method(method_id: str, body: urr.CheckRequest):
    try:
        profile = ontology.method_profile(method_id)
    except ValueError:
        profile = None
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Unknown method: {method_id}")

    reject_unknown_variables(body.available_variables)

    return engine.check_method(profile, set(body.available_variables))

@app.post("/urr/validate")
def validate_urr(body: urr.URR):
    return urr.validate(body)


@app.post("/recommend")
def recommend(body: urr.URR):
    validated = urr.validate(body)
    if not validated["valid"]:
        raise HTTPException(status_code=422, detail=validated["problems"])
    return engine.recommend(validated)


@app.post("/options/{step}")
def step_options(step: str, draft: urr.Draft):
    try:
        return options.get_options(step, draft)
    except options.StepError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error))
@app.post("/reach")
def reach(body: urr.CheckRequest):
    reject_unknown_variables(body.available_variables)
    return {"challenges": engine.reach(set(body.available_variables))}
@app.post("/datasets")
def datasets(body: urr.DatasetRequest):
    reject_unknown_variables(body.variables)
    return {"datasets": engine.find_datasets(set(body.variables))}
@app.post("/workflow")
def workflow(body: urr.WorkflowRequest):
    validated = urr.validate(body)
    if not validated["valid"]:
        raise HTTPException(status_code=422, detail=validated["problems"])
    return engine.workflow(validated, body.methods)

@app.get("/vocabulary/{kind}")
def vocabulary(kind: str):
    """Values of one question type: objective, intent, scenario, entity, driver, output."""
    if kind not in ontology.VOCABULARIES:
        raise HTTPException(status_code=404, detail=f"Unknown vocabulary: {kind}")
    return ontology.list_vocabulary(kind)


@app.get("/challenges/{challenge_id}/outputs")
def challenge_outputs(challenge_id: str):
    require_challenge(challenge_id)
    return ontology.list_outputs(challenge_id)


@app.get("/challenges/{challenge_id}/drivers")
def challenge_drivers(challenge_id: str):
    require_challenge(challenge_id)
    return ontology.list_drivers(challenge_id)

@app.post("/requirements")
def requirements_of_urr(urr: URR):
    """The requirements implied by what the user chose (hard first)."""
    checked = validate(urr)
    if not checked["valid"]:
        raise HTTPException(status_code=422, detail=checked["problems"])
    return requirements.collect(urr)

@app.post("/rules/check")
def rules_check(urr: URR):
    """For every method of the challenge: excluded or not, score change, and why."""
    checked = validate(urr)
    if not checked["valid"]:
        raise HTTPException(status_code=422, detail=checked["problems"])
    return rules.judge_methods(urr)