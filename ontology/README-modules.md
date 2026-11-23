# AIO ontology modules (0.9.0)

Since 0.9.0 the AIO ontology is a **core** and **extensions**, each with its own namespace,
file and graph in GraphDB. The core holds the knowledge model; the extensions hold what the
recommendation system needs on top of it.

| Module | Prefix | Namespace | Files | Imports |
|---|---|---|---|---|
| Core | `aio:` | `https://w3id.org/aio#` | `aio-core.ttl`, `aio-additions.ttl` (drafts), `aio-deprecated.ttl` | – |
| Study requirements | `aioreq:` | `https://w3id.org/aio/requirements#` | `aio-requirements.ttl` | core |
| Model composition | `aiowf:` | `https://w3id.org/aio/workflow#` | `aio-workflow.ttl` | core |
| Software implementations | `aiosw:` | `https://w3id.org/aio/software#` | `aio-software.ttl`, `aio-software-generated.ttl` | core, model composition |
| Alignments | – | `https://w3id.org/aio/alignments` | `aio-alignments.ttl` | core |

**Core**: the four axes — problem definition (water challenge, objective, intent, scenario,
expected output), water system definition (water entities, processes, variables, factors),
modelling definition (methods, software platforms) and data representation (datasets, data
variables, provenance, derivations) — and the value sets that describe them (time-step class,
temporal mode, spatial representation, dimensionality, application scale, output form,
temporal nature, licence category, geographic area).

**Study requirements**: the rules a study implies (forecasting → continuous simulation...),
their strength and weight, and which challenge, objective or output implies them.

**Model composition**: component roles, which method fills which role, role interfaces (the
variables roles exchange), chain templates and their slots, coupling types, `canFeed`.

**Software implementations**: software modules (a method inside a software, with its usual
time step and resolution) and curated reference chains with their steps.

## Rules

- A term keeps its **local name** in every module (`aio:fillsRole` became `aiowf:fillsRole`).
  Local names are unique across modules; the backend works with them and asks GraphDB for the
  full IRI (`backend/app/queries.py: iri`).
- **The core never refers to an extension.** A statement about a core term that uses an
  extension property ("SCS-CN fills role excess rainfall") belongs to the extension.
- Every class and property has `rdfs:isDefinedBy` its module.
- The IRIs of 0.8.0 that moved are listed in `aio-deprecated.ttl` (`owl:deprecated`,
  `dct:isReplacedBy`).

## Editing

- Open a module in Protégé: `catalog-v001.xml` makes its imports load from this folder.
- `aio-software-generated.ttl` is written by `build_software_ttl.py`; edit its tables, not the file.
- After a change, reload the module's graph in GraphDB (graph name = the module IRI), e.g.

      curl -X PUT -H "Content-Type: text/turtle" --data-binary @aio-workflow.ttl \
        "http://localhost:7200/repositories/aio/rdf-graphs/service?graph=https%3A%2F%2Fw3id.org%2Faio%2Fworkflow"

  then `POST /refresh` on the backend. A fresh `docker compose up` loads every module.

## How 0.9.0 was made

`tools/split_into_modules.py` split the 0.8.0 files (kept in `backup-0.8.0-before-modules/`)
using `tools/membership-0.9.0.json` (which module each moved term belongs to, from the domains
and ranges of the properties). It checks its output against the source, triple for triple.
The portal's answers to 138 reference requests were compared before and after: identical in
content; only the order of some lists changed, and the backend now sorts them so a reload can
no longer change it.
