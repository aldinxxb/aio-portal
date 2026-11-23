import re

from app.config import MODULES, ONTOLOGY_NS, QUERIES_DIR

# A name may contain only letters, digits, "_" and "-". Nothing else gets through.
SAFE_NAME = re.compile(r"^[A-Za-z0-9_\-]+$")


def load(name: str) -> str:
    """Read a .rq file from the queries folder."""
    return (QUERIES_DIR / f"{name}.rq").read_text(encoding="utf-8")


def check_name(value: str) -> str:
    """Refuse anything that is not a plain concept name."""
    if not isinstance(value, str) or not SAFE_NAME.match(value):
        raise ValueError(f"Invalid concept name: {value!r}")
    return value


def build(name: str, **concepts: str) -> str:
    """Load a template and fill each {{placeholder}} with a checked ontology IRI."""
    text = load(name)
    for key, value in concepts.items():
        placeholder = "{{" + key + "}}"
        if placeholder not in text:
            raise ValueError(f"Template {name!r} has no placeholder {placeholder}")
        text = text.replace(placeholder, f"<{iri(check_name(value))}>")
    return text

# ---- the module of each term ------------------------------------------------------------------
# Terms of the extensions live in their own namespace (aiowf:fillsRole). Which one is read
# once from GraphDB: every IRI declared in an extension namespace. Anything else is core.
_extension_iris: dict[str, str] | None = None


def iri(name: str) -> str:
    """The full IRI of a term given by its local name, in the module that defines it."""
    global _extension_iris
    if _extension_iris is None:
        from app.sparql_client import run_select           # here: queries.py stays importable without GraphDB
        filters = " || ".join(f'STRSTARTS(STR(?s), "{m["namespace"]}")' for k, m in MODULES.items() if k != "core")
        rows = run_select(f"SELECT DISTINCT ?s WHERE {{ ?s ?p ?o FILTER(isIRI(?s) && ({filters})) }}")
        _extension_iris = {r["s"].split("#")[-1]: r["s"] for r in rows}
    return _extension_iris.get(name, ONTOLOGY_NS + name)


def clear_names() -> None:
    """Forget the term -> IRI table (after reloading the ontology)."""
    global _extension_iris
    _extension_iris = None
