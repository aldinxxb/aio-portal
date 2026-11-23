import os
from pathlib import Path

GRAPHDB_URL = os.getenv("GRAPHDB_URL", "http://localhost:7200")
GRAPHDB_REPO = os.getenv("GRAPHDB_REPO", "aio")

ONTOLOGY_NS = "https://w3id.org/aio#"           # the core

# Since 0.9.0 the ontology is a core and three extensions, each in its own namespace. A term
# keeps its local name in every module ("fillsRole", "ChainStep"...), and local names are
# unique across modules, so the backend works with local names and asks GraphDB for the
# full IRI when it writes a query (queries.iri).
MODULES = {
    "core": {"prefix": "aio", "namespace": ONTOLOGY_NS, "iri": "https://w3id.org/aio"},
    "requirements": {"prefix": "aioreq", "namespace": "https://w3id.org/aio/requirements#", "iri": "https://w3id.org/aio/requirements"},
    "workflow": {"prefix": "aiowf", "namespace": "https://w3id.org/aio/workflow#", "iri": "https://w3id.org/aio/workflow"},
    "software": {"prefix": "aiosw", "namespace": "https://w3id.org/aio/software#", "iri": "https://w3id.org/aio/software"},
}
NAMESPACES = [m["namespace"] for m in MODULES.values()]

QUERIES_DIR = Path(__file__).resolve().parent.parent / "queries"

# How much each criterion counts in the score (they add up to 1).
WEIGHTS = {"input_coverage": 0.7, "process_match": 0.3}

# Web addresses allowed to call this API from a browser (comma-separated).
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")

# A method with at most this many calibration parameters counts as "few".
FEW_CALIBRATION_PARAMETERS = 2
# ---- Set-up diagnosis (Modeling Approach entry). Starting values, to tune later. ----
FIT_START = 100
FIT_PENALTY = {"blocking": 30, "warning_high": 10, "warning": 4, "info": 1}
FIT_GOOD = 80              # at least this, and nothing blocking -> "fit"
FIT_PARTLY = 40            # at least this, or at most 2 blocking issues -> "partly fit"
MAX_CALIBRATION_PARAMETERS = 6   # "few calibration parameters" for a whole set-up
REPLACE_GAIN = 20          # an alternative method is proposed if it scores this much higher
MAX_ACTIONS = 18           # actions returned by /setup/improve
MAX_PER_KIND = 3           # candidates kept per kind of action and subject
