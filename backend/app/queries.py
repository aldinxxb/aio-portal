import re

from app.config import ONTOLOGY_NS, QUERIES_DIR

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
        text = text.replace(placeholder, f"<{ONTOLOGY_NS}{check_name(value)}>")
    return text