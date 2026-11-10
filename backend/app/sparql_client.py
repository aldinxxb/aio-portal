import httpx

from app.config import GRAPHDB_REPO, GRAPHDB_URL


def run_select(query: str) -> list[dict]:
    """Send a SPARQL SELECT query to GraphDB and return the rows as simple dictionaries."""
    url = f"{GRAPHDB_URL}/repositories/{GRAPHDB_REPO}"
    response = httpx.post(
        url,
        data={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=30,
    )
    response.raise_for_status()
    bindings = response.json()["results"]["bindings"]
    # each row looks like {"label": {"type": "literal", "value": "flood"}}
    # we keep only the values: {"label": "flood"}
    return [{name: cell["value"] for name, cell in row.items()} for row in bindings]
    