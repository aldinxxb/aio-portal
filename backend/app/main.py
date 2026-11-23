import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from app import chains, engine, geo, ontodoc, knowledge, ontology, opendata, options, urr, requirements, rules, setup
from app.urr import URR, validate
from app.config import CORS_ORIGINS


WIZARD_STEPS = ("challenge", "objective", "driver", "output", "process", "variable",
                "datastep", "scale", "timestep", "software", "data")


def warm_up() -> None:
    """Ask, once at startup, every question the wizard will ask, so that no visitor waits
    for GraphDB: the ontology snapshot, then each step's options for each challenge, then
    the workflows. Answers stay in memory until POST /refresh."""
    try:
        knowledge.load()
        ontology.requirements_of("")
        for challenge in ontology.list_challenges():
            draft = urr.Draft(challenge=challenge["id"])
            for step in WIZARD_STEPS:
                try:
                    options.get_options(step, draft)
                except Exception:          # a step that needs more answers: skipped
                    pass
            engine.chains_for(urr.validate(urr.URR(challenge=challenge["id"])))
    except Exception:                      # GraphDB not ready yet: the first request will read it
        pass
    for name in geo.LAYERS:                # the map layers (fetched and simplified once, then on disk)
        try:
            geo.layer(name)
        except Exception:                  # offline: the map says so when it is opened
            pass
    try:
        geo.all_watersheds()               # BD Topage watersheds (100 MB once, then a few MB on disk)
    except Exception:
        pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    threading.Thread(target=warm_up, daemon=True).start()
    yield


app = FastAPI(title="AIO Portal API", lifespan=lifespan)

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


@app.post("/refresh")
def refresh():
    """Forget everything kept in memory: call it after reloading the ontology in GraphDB."""
    knowledge.load(force=True)
    ontodoc.clear()
    threading.Thread(target=warm_up, daemon=True).start()
    return {"status": "refreshed"}


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
@app.get("/datasets/search")
def search_datasets(q: str = ""):
    """All datasets containing a variable whose name matches q, with temporal and spatial facts."""
    return engine.search_datasets(q.strip())


@app.get("/datasets/variables")
def dataset_variables():
    """The variables that at least one dataset provides (suggestions for the search box)."""
    return engine.dataset_variables()


@app.get("/datasets/suggestions")
def dataset_suggestions():
    """Variable names and dataset names that the search box can propose."""
    return engine.dataset_suggestions()


@app.post("/chains")
def recommend_chains(body: urr.ChainRequest):
    """Recommended workflows: chains of methods (reference chains first, then generated ones)."""
    validated = urr.validate(body)
    if not validated["valid"]:
        raise HTTPException(status_code=422, detail=validated["problems"])
    if body.licence not in (None, "open", "free"):
        raise HTTPException(status_code=422, detail=f"Unknown licence filter: {body.licence}")
    if body.software and body.software not in knowledge.load().software:
        raise HTTPException(status_code=422, detail=f"Unknown software: {body.software}")
    return engine.chains_for(validated, body.licence, body.software)


@app.post("/methods/{method_id}/combine")
def combine_method(method_id: str, body: urr.CombineRequest):
    """Around one method: who feeds it, whom it feeds, alternatives, chains, where its data comes from."""
    k = knowledge.load()
    if method_id not in k.facts:
        raise HTTPException(status_code=404, detail=f"Unknown method: {method_id}")
    reject_unknown_variables(body.available_variables)
    return chains.combine(k, method_id, body.software, set(body.available_variables))


# ---- Modeling Approach entry: diagnose a set-up and improve it --------------------

def run_setup(action, *args):
    """Run a set-up function; an unknown name in the request becomes a 422 error."""
    try:
        return action(*args)
    except setup.SetupError as error:
        raise HTTPException(status_code=422, detail=error.problems)


@app.post("/setup/options")
def setup_options(body: setup.OptionsRequest):
    """Options of one step of the set-up wizard, each with a status and a reason."""
    return run_setup(setup.options, knowledge.load(), body.step, body.request)


@app.post("/setup/diagnose")
def setup_diagnose(body: setup.SetupRequest):
    """How well does this set-up fit the study? Checks, issues and a fit score."""
    k = knowledge.load()
    request, warnings = run_setup(setup.normalise, k, body)
    return setup.diagnose(k, request, warnings=warnings)


@app.post("/setup/improve")
def setup_improve(body: setup.SetupRequest):
    """The diagnosis plus the actions that would improve the set-up (each with a patch)."""
    k = knowledge.load()
    request, warnings = run_setup(setup.normalise, k, body)
    return setup.improve(k, request, warnings)


# ---- Start from data: map layers and the open-data entry --------------------------------

# ---- The AIO ontology: documentation and browser (like a published ontology page) ------

ONTOLOGY_VIEWS = ("core", "requirements", "workflow", "software", "all")


@app.get("/ontology")
def ontology_overview(module: str = "core"):
    """One module of the AIO ontology (core by default, an extension, or all): metadata, counts,
    class hierarchy and main relations, with the list of modules."""
    if module not in ONTOLOGY_VIEWS:
        raise HTTPException(status_code=422, detail=f"module: one of {', '.join(ONTOLOGY_VIEWS)}")
    return ontodoc.overview(module)


@app.get("/ontology/terms")
def ontology_terms(module: str = "all"):
    """Every class and property (of one module, or all), with its label, definition and parent."""
    if module not in ONTOLOGY_VIEWS:
        raise HTTPException(status_code=422, detail=f"module: one of {', '.join(ONTOLOGY_VIEWS)}")
    return ontodoc.term_list(module)


@app.get("/ontology/search")
def ontology_search(q: str = ""):
    """Classes, properties and individuals whose name or definition contains every word."""
    return ontodoc.search(q.strip())


@app.get("/ontology/export")
def ontology_export(format: str = "ttl", part: str = "schema"):
    """The ontology as a file: Turtle, RDF/XML, JSON-LD or N-Triples; the schema only or everything."""
    if format not in ontodoc.FORMATS or part not in ontodoc.PARTS:
        raise HTTPException(status_code=422, detail=f"format: ttl, rdf, jsonld or nt; part: {', '.join(ontodoc.PARTS)}")
    try:
        body, media_type, filename = ontodoc.export(format, part)
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Export not available: {error}")
    return Response(body, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/ontology/{term_id}")
def ontology_term(term_id: str):
    """One term in full: hierarchy, domain and range, restrictions, uses, instances."""
    found = ontodoc.term(term_id)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Unknown term: {term_id}")
    return found


@app.get("/geo/layers")
def geo_layers():
    """The map layers of metropolitan France that can be shown to choose a study area."""
    return geo.layers()


@app.get("/geo/watersheds/{layer}/{area_id}")
def geo_watersheds(layer: str, area_id: str):
    """The topographic watersheds (BD Topage) whose centre lies inside one study area."""
    if layer not in geo.LAYERS:
        raise HTTPException(status_code=404, detail=f"Unknown layer: {layer}")
    try:
        return geo.watersheds_in(layer, area_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown area: {area_id}")
    except Exception as error:             # the public source cannot be reached
        raise HTTPException(status_code=503, detail=f"Watersheds not available: {error}")


@app.get("/geo/{layer}")
def geo_layer(layer: str):
    """One layer as simplified GeoJSON: each feature has an id, a name and a bounding box."""
    if layer not in geo.LAYERS:
        raise HTTPException(status_code=404, detail=f"Unknown layer: {layer}")
    try:
        return geo.layer(layer)
    except Exception as error:             # the public source cannot be reached
        raise HTTPException(status_code=503, detail=f"Map layer not available: {error}")


@app.get("/opendata/variables")
def opendata_variables():
    """The variables a user can declare, with the role they play and how much open data exists."""
    return opendata.declarable_variables(knowledge.load())


@app.post("/opendata/assess")
def opendata_assess(body: opendata.AssessRequest):
    """Everything the answers given so far allow: open data of the area, roles, what the data
    enables, objectives and outputs reachable first, workflows and the next dataset to add."""
    k = knowledge.load()
    unknown = [d.variable for d in body.data if d.variable not in k.labels]
    if body.challenge and body.challenge not in k.challenges:
        unknown.append(body.challenge)
    if unknown:
        raise HTTPException(status_code=422, detail=[f"Unknown: {u}" for u in unknown])
    return opendata.assess(k, body)


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