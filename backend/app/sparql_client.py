import os
import threading
import time

import httpx

from app.config import GRAPHDB_REPO, GRAPHDB_URL

# One client for the whole application: it keeps the connection to GraphDB open,
# so a query costs a few milliseconds instead of a new connection every time.
client = httpx.Client(timeout=30)

# The ontology does not change while the portal runs, and the same questions are asked
# again and again. Each answer is kept until the ontology is reloaded: call clear_cache()
# (POST /refresh does it). A time limit made every idle user pay the cold cost again.
# SPARQL_CACHE_SECONDS sets a limit anyway (0 = no cache).
CACHE_SECONDS = float(os.getenv("SPARQL_CACHE_SECONDS", "inf"))
_cache: dict[str, tuple[float, list[dict]]] = {}
_lock = threading.Lock()


def clear_cache() -> None:
    with _lock:
        _cache.clear()
    from app import queries                                  # the term -> IRI table is read from the same data
    queries.clear_names()


def run_select(query: str) -> list[dict]:
    """Send a SPARQL SELECT query to GraphDB and return the rows as simple dictionaries."""
    kept = _cache.get(query)
    if kept and time.monotonic() - kept[0] < CACHE_SECONDS:
        return [dict(row) for row in kept[1]]      # a copy: the caller may change its rows

    url = f"{GRAPHDB_URL}/repositories/{GRAPHDB_REPO}"
    response = client.post(
        url,
        data={"query": query},
        headers={"Accept": "application/sparql-results+json"},
    )
    response.raise_for_status()
    bindings = response.json()["results"]["bindings"]
    # each row looks like {"label": {"type": "literal", "value": "flood"}}
    # we keep only the values: {"label": "flood"}
    rows = [{name: cell["value"] for name, cell in row.items()} for row in bindings]
    if CACHE_SECONDS > 0:
        with _lock:
            _cache[query] = (time.monotonic(), rows)
    return [dict(row) for row in rows]
