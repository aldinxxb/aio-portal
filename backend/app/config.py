import os
from pathlib import Path

GRAPHDB_URL = os.getenv("GRAPHDB_URL", "http://localhost:7200")
GRAPHDB_REPO = os.getenv("GRAPHDB_REPO", "aio")

ONTOLOGY_NS = "https://w3id.org/aio#"

QUERIES_DIR = Path(__file__).resolve().parent.parent / "queries"

# How much each criterion counts in the score (they add up to 1).
WEIGHTS = {"input_coverage": 0.7, "process_match": 0.3}

# Web addresses allowed to call this API from a browser (comma-separated).
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")

# A method with at most this many calibration parameters counts as "few".
FEW_CALIBRATION_PARAMETERS = 2