# AIO – Hydrology Decision Support portal

An ontology-driven portal that helps hydrologists choose models and open data for a water study.
It is developed in the **AIO – Agir et Innover pour l'Eau** project (Université Côte d'Azur, GéoAzur, IMREDD).

The portal has four entries:

| Entry | Question it answers |
|---|---|
| **Start from data** (home) | *What can I do with my data, here?* Choose a study area of France (river basins down to BD Topage watersheds), declare your data, discover the open data of the area, and get the workflows you can run. |
| **Start from a modeling approach** | *Does my method or software fit my study?* Describe your set-up; the portal diagnoses it, checks its data and proposes improvements. |
| **Start from a water challenge** | *Which models and data fit my water issue?* Ranked workflows for a challenge, objective and expected output. |
| **AIO ontology** | Browse the ontology behind the recommendations: classes, properties, diagrams, alignments, downloads. |

Every study has a shareable link, and a diagnosis can be exported as a report (PDF or Markdown).

## The AIO ontology (0.9.0)

A core and three extensions, each in its own namespace and named graph:

| Module | Namespace | Content |
|---|---|---|
| core | `https://w3id.org/aio#` | water system, problem, data and modelling axes |
| requirements | `https://w3id.org/aio/requirements#` | what methods and objectives require |
| workflow | `https://w3id.org/aio/workflow#` | workflows, templates, roles |
| software | `https://w3id.org/aio/software#` | software and their modules |

Alignments to ENVO, SWEET, BFO, RO, SOSA, schema.org and I-ADOPT are in `ontology/aio-alignments.ttl`;
see [`ontology/README-modules.md`](ontology/README-modules.md).

## Architecture

```
ontology/   Turtle files of the modules (loaded into GraphDB, one named graph each)
graphdb/    GraphDB repository configuration and sample queries
backend/    FastAPI service: SPARQL queries (backend/queries/*.rq), recommendation engine, open data, geo layers
frontend/   React + TypeScript + Vite single-page app
```

## Running it

With Docker:

```
docker compose up --build
```

- portal: http://localhost:8080
- API: http://localhost:8000 (OpenAPI docs at `/docs`)
- GraphDB: http://localhost:7200 (repository `aio`, loaded with the ontology modules on start)

For development, run GraphDB with Docker, then:

```
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Linux/macOS: .venv/bin/pip
.venv/Scripts/uvicorn app.main:app --reload --port 8000
cd frontend && npm install && npm run dev
```

Backend tests: `cd backend && .venv/Scripts/python -m pytest -q`.

Geographic layers (Sandre river basins, IGN regions and departments, BD Topage watersheds) are fetched on first use and cached in `backend/cache/`.
