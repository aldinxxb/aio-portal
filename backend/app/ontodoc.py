"""Documentation of the AIO ontology, built from the triples asserted in GraphDB.

What a published ontology page (SAREF4WATR, Widoco...) gives, served as JSON for the portal:
  overview   metadata, namespaces, counts, the class hierarchy, the main relations
  terms      every class and property (and, on demand, individuals) for the browser
  term       one term in full: hierarchy, domain/range, restrictions, uses, instances
  export     the ontology in Turtle, RDF/XML, JSON-LD or N-Triples (schema or full)

Only asserted triples are read (GraphDB's explicit graph), so the page shows the model as
written. Everything is read once and kept (the ontology does not change while the portal
runs; POST /refresh clears it with the other caches).

Layering: ontodoc.py -> sparql_client.py, queries.py, config.py.
"""
import threading
from collections import defaultdict

import httpx

from app import queries
from app.config import GRAPHDB_REPO, GRAPHDB_URL, MODULES, NAMESPACES, ONTOLOGY_NS
from app.sparql_client import run_select

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
OWL = "http://www.w3.org/2002/07/owl#"
SKOS = "http://www.w3.org/2004/02/skos/core#"
DCT = "http://purl.org/dc/terms/"
VANN = "http://purl.org/vocab/vann/"
ONTOLOGY_IRI = ONTOLOGY_NS.rstrip("#")

KINDS = {
    OWL + "Class": "class",
    OWL + "ObjectProperty": "object",
    OWL + "DatatypeProperty": "datatype",
    OWL + "AnnotationProperty": "annotation",
}
CHARACTERISTICS = {
    OWL + "FunctionalProperty": "functional", OWL + "InverseFunctionalProperty": "inverse functional",
    OWL + "TransitiveProperty": "transitive", OWL + "SymmetricProperty": "symmetric",
    OWL + "AsymmetricProperty": "asymmetric", OWL + "ReflexiveProperty": "reflexive",
    OWL + "IrreflexiveProperty": "irreflexive",
}
PREFIXES = {
    ONTOLOGY_NS: "aio", RDF: "rdf", RDFS: "rdfs", OWL: "owl", SKOS: "skos", DCT: "dct", VANN: "vann",
    "http://www.w3.org/2001/XMLSchema#": "xsd", "http://www.w3.org/ns/dcat#": "dcat",
    "http://xmlns.com/foaf/0.1/": "foaf", "http://qudt.org/schema/qudt/": "qudt",
    "http://qudt.org/vocab/unit/": "unit", "http://www.opengis.net/ont/geosparql#": "geo",
    "http://www.w3.org/ns/sosa/": "sosa", "https://schema.org/": "schema",
    "http://purl.obolibrary.org/obo/": "obo", "https://w3id.org/iadopt/ont/": "iop",
    "http://sweetontology.net/": "sweet",
    **{m["namespace"]: m["prefix"] for m in MODULES.values()},
}
# the modules of AIO (0.9.0): a core and extensions, each in its own namespace and graph
# Vocabularies whose terms AIO reuses as they are (same IRI): standard practice, so that a
# dataset described by AIO is a dcat:Dataset for any DCAT tool. Distinct from the alignments
# (ENVO, SWEET...), which only map AIO terms to other ones.
REUSED = {
    "http://www.w3.org/ns/dcat#": ("DCAT", "Data Catalog Vocabulary (W3C)", "https://www.w3.org/TR/vocab-dcat-3/"),
    "http://purl.org/dc/terms/": ("DCTERMS", "Dublin Core Metadata Terms (DCMI)", "https://www.dublincore.org/specifications/dublin-core/dcmi-terms/"),
    "http://xmlns.com/foaf/0.1/": ("FOAF", "Friend of a Friend", "http://xmlns.com/foaf/spec/"),
    "http://qudt.org/schema/qudt/": ("QUDT", "Quantities, Units, Dimensions and Types", "https://qudt.org/"),
    "http://qudt.org/vocab/unit/": ("QUDT", "Quantities, Units, Dimensions and Types", "https://qudt.org/"),
    "http://www.opengis.net/ont/geosparql#": ("GeoSPARQL", "OGC GeoSPARQL", "https://www.ogc.org/standard/geosparql/"),
    "http://www.w3.org/2004/02/skos/core#": ("SKOS", "Simple Knowledge Organization System (W3C)", "https://www.w3.org/TR/skos-reference/"),
    "http://purl.org/vocab/vann/": ("VANN", "Vocabulary for annotating vocabulary descriptions", "https://vocab.org/vann/"),
}


def reused_vocabulary(iri: str) -> tuple | None:
    for ns, info in REUSED.items():
        if iri.startswith(ns):
            return info
    return None


MODULE_TITLES = {"core": "Core", "requirements": "Study requirements", "workflow": "Model composition",
                 "software": "Software implementations"}
ALIGNMENTS_IRI = "https://w3id.org/aio/alignments"
# the four axes of the core; its other top-level classes are value sets that describe them
CORE_AXES = ["ProblemDefinition", "WaterSystemDefinition", "ModelingDefinition", "DataRepresentation"]


def module_of(iri: str) -> str | None:
    """core / requirements / workflow / software for an AIO term, None otherwise."""
    for key, spec in sorted(MODULES.items(), key=lambda x: -len(x[1]["namespace"])):
        if iri.startswith(spec["namespace"]):
            return key
    return None
# the external vocabularies AIO is aligned to (module aio-alignments), recognised from the
# rdfs:isDefinedBy of each external term, else from its IRI
VOCABULARIES = [
    ("envo", "ENVO", "Environment Ontology"), ("ENVO_", "ENVO", "Environment Ontology"),
    ("sweetontology", "SWEET", "Semantic Web for Earth and Environment Technology"),
    ("iadopt", "I-ADOPT", "InteroperAble Descriptions of Observable Property Terminology"),
    ("obo/bfo", "BFO", "Basic Formal Ontology"), ("BFO_", "BFO", "Basic Formal Ontology"),
    ("obo/ro", "RO", "OBO Relation Ontology"), ("RO_", "RO", "OBO Relation Ontology"),
    ("ns/sosa", "SOSA", "Sensor, Observation, Sample and Actuator"), ("schema.org", "schema.org", "schema.org"),
]
MAPPINGS = {
    SKOS + "exactMatch": "exact match", SKOS + "closeMatch": "close match", SKOS + "broadMatch": "broader match",
    SKOS + "narrowMatch": "narrower match", SKOS + "relatedMatch": "related match", SKOS + "related": "related",
    RDFS + "subClassOf": "subclass of", RDFS + "subPropertyOf": "subproperty of",
    OWL + "equivalentClass": "equivalent class", OWL + "equivalentProperty": "equivalent property",
}
# annotations shown in their own place on a term card, not in the generic list
SHOWN_APART = {RDF + "type", RDFS + "label", SKOS + "definition", RDFS + "comment", RDFS + "subClassOf",
               RDFS + "subPropertyOf", RDFS + "domain", RDFS + "range", OWL + "inverseOf",
               OWL + "equivalentClass", OWL + "disjointWith", OWL + "propertyChainAxiom",
               OWL + "propertyDisjointWith", OWL + "unionOf",
               SKOS + "exactMatch", SKOS + "closeMatch", SKOS + "broadMatch", SKOS + "narrowMatch",
               SKOS + "relatedMatch", SKOS + "related"}
FORMATS = {
    "ttl": ("text/turtle", "ttl"),
    "rdf": ("application/rdf+xml", "rdf"),
    "jsonld": ("application/ld+json", "jsonld"),
    "nt": ("application/n-triples", "nt"),
}

_lock = threading.Lock()
_model: dict = {}


def clear() -> None:
    with _lock:
        _model.clear()


def curie(iri: str) -> str:
    """https://w3id.org/aio#Challenge -> aio:Challenge (the IRI itself when no prefix is known)."""
    for ns, prefix in sorted(PREFIXES.items(), key=lambda x: -len(x[0])):
        if iri.startswith(ns):
            return f"{prefix}:{iri[len(ns):]}"
    return iri


def local(iri: str) -> str:
    """The local name of an AIO term (unique across the modules), the CURIE of anything else."""
    return iri.split("#", 1)[1] if module_of(iri) else curie(iri)


# ----------------------------------------------------------------------------
# Loading: every asserted triple, grouped by subject
# ----------------------------------------------------------------------------

def model() -> dict:
    if _model:
        return _model
    with _lock:
        if _model:
            return _model
        out: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        incoming: dict[str, list] = defaultdict(list)
        for row in run_select(queries.load("ontology_triples")):
            s = ("_:" if row["st"] == "b" else "") + row["s"]
            o = row["o"]
            if row["ot"] == "b":
                o = {"bnode": "_:" + o}
            elif row["ot"] == "l":
                o = {"value": o, "lang": row.get("lang") or None,
                     "datatype": curie(row["dt"]) if row.get("dt") and not row["dt"].endswith("#string")
                     and not row["dt"].endswith("langString") else None}
            out[s][row["p"]].append(o)
            if isinstance(o, str):
                incoming[o].append((s, row["p"]))
        _model["out"] = out
        _model["in"] = incoming
        _build(_model)
    return _model


def _text(values: list, lang: str = "en") -> str | None:
    """The literal in the wanted language, else one without language, else any."""
    literals = [v for v in values if isinstance(v, dict) and "value" in v]
    for test in (lambda v: v["lang"] == lang, lambda v: not v["lang"], lambda v: True):
        found = next((v["value"] for v in literals if test(v)), None)
        if found is not None:
            return found
    return None


def _readable(name: str) -> str:
    """dct:PeriodOfTime -> period of time; unit:MilliM-PER-DAY stays as it is."""
    local_part = name.split(":", 1)[-1]
    if "-" in local_part or local_part.isupper():
        return local_part
    return " ".join(w.lower() for w in __import__("re").findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", local_part)) or local_part


def _reused_terms(out: dict) -> dict[str, dict]:
    """External terms AIO declares or uses (classes, properties, units), with how often."""
    found: dict[str, dict] = {}

    def add(iri: str, kind: str) -> None:
        if iri.startswith("_:") or module_of(iri) or not reused_vocabulary(iri):
            return
        entry = found.setdefault(iri, {"kind": kind, "uses": 0})
        if entry["kind"] == "property" and kind != "property":
            entry["kind"] = kind
        entry["uses"] += 1

    for s, props in out.items():
        types = [t for t in props.get(RDF + "type", []) if isinstance(t, str)]
        if not module_of(s) and reused_vocabulary(s):          # declared in an AIO file
            kind = next((KINDS[t] for t in types if t in KINDS), None) \
                or ("individual" if OWL + "NamedIndividual" in types else "datatype" if RDFS + "Datatype" in types else None)
            if kind:
                found.setdefault(s, {"kind": kind, "uses": 0})
        if not module_of(s):
            continue
        for p, values in props.items():
            add(p, "property")
            for v in values:
                if isinstance(v, str):
                    add(v, "class" if p == RDF + "type" else "individual" if p.endswith("hasUnit") else "class")
    for iri, entry in found.items():
        if entry["kind"] == "property":
            entry["kind"] = "annotation"
    return found


def _build(m: dict) -> None:
    out = m["out"]
    terms: dict[str, dict] = {}
    reused = _reused_terms(out)
    for s, props in out.items():
        if s.startswith("_:") or not module_of(s):
            continue
        types = [t for t in props.get(RDF + "type", []) if isinstance(t, str)]
        kind = next((KINDS[t] for t in types if t in KINDS), None)
        if kind is None and (OWL + "NamedIndividual" in types or any(module_of(t) or t in reused for t in types)):
            kind = "individual"
        if kind is None:
            continue
        terms[s] = {"iri": s, "id": local(s), "kind": kind,
                    "label": _text(props.get(RDFS + "label", [])) or local(s),
                    "definition": _text(props.get(SKOS + "definition", [])) or _text(props.get(RDFS + "comment", [])),
                    "types": [t for t in types if module_of(t) or (t in reused and reused[t]["kind"] == "class")],
                    "module": module_of(s)}
    for iri, info in reused.items():
        vocabulary = reused_vocabulary(iri)
        props = out.get(iri, {})
        terms[iri] = {"iri": iri, "id": curie(iri), "kind": info["kind"],
                      "label": _text(props.get(RDFS + "label", [])) or _readable(curie(iri)),
                      "definition": _text(props.get(SKOS + "definition", [])) or _text(props.get(RDFS + "comment", [])),
                      "types": [], "module": None, "reused": vocabulary[0], "uses": info["uses"]}
    m["terms"] = terms
    m["by_id"] = {t["id"]: iri for iri, t in terms.items()}

    def parents(iri: str, prop: str) -> list[str]:
        return [p for p in out.get(iri, {}).get(prop, []) if isinstance(p, str)]

    children: dict[str, list[str]] = defaultdict(list)
    for iri, t in terms.items():
        prop = RDFS + "subClassOf" if t["kind"] == "class" else RDFS + "subPropertyOf" if t["kind"] in ("object", "datatype", "annotation") else None
        if prop:
            for p in parents(iri, prop):
                children[p].append(iri)
    m["children"] = children
    instances: dict[str, list[str]] = defaultdict(list)
    for iri, t in terms.items():
        if t["kind"] == "individual":
            for c in t["types"]:
                instances[c].append(iri)
    m["instances"] = instances


# ----------------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------------

def ref(iri: str) -> dict:
    """A term as a link: id, label, kind; external terms keep their CURIE."""
    t = model()["terms"].get(iri)
    if t:
        found = {"id": t["id"], "label": t["label"], "kind": t["kind"], "iri": iri, "external": False, "module": t["module"]}
        if t.get("reused"):
            found["reused"] = t["reused"]
        return found
    short = curie(iri)
    own = model()["out"].get(iri, {})
    name = _text(own.get(RDFS + "label", []))
    vocabulary = vocabulary_of(iri)
    if name:
        label = name
    elif ":" in short and not short.startswith("http"):
        label = f"{short.split(':', 1)[1]} ({short.split(':', 1)[0]})"
    else:
        label = short
    return {"id": short, "label": label, "kind": "external", "iri": iri, "external": True, "vocabulary": vocabulary}


def vocabulary_of(iri: str) -> str | None:
    """The external vocabulary a term comes from (ENVO, SWEET, BFO...), None for the W3C basics."""
    sources = [s for s in model()["out"].get(iri, {}).get(RDFS + "isDefinedBy", []) if isinstance(s, str)]
    for text in sources + [iri]:
        for key, short, _ in VOCABULARIES:
            if key in text:
                return short
    return None


def alignments_of(iri: str) -> list[dict]:
    """How one AIO term maps to external vocabularies: SKOS matches and links to external classes."""
    found = []
    for prop, relation in MAPPINGS.items():
        for target in model()["out"].get(iri, {}).get(prop, []):
            if isinstance(target, str) and not module_of(target) and vocabulary_of(target):
                found.append({"relation": relation, "target": ref(target)})
    return found


def _expr(node, depth: int = 0):
    """A blank node (union, property chain, restriction...) as a small readable tree."""
    out = model()["out"]
    if isinstance(node, str):
        return ref(node)
    if "value" in node:
        return {"literal": node["value"]}
    props = out.get(node["bnode"], {})
    if depth > 6:
        return {"text": "…"}
    if RDF + "first" in props:                                   # an RDF list
        items, current = [], node
        while isinstance(current, dict) and "bnode" in current and depth < 50:
            cell = out.get(current["bnode"], {})
            if RDF + "first" not in cell:
                break
            items.append(_expr(cell[RDF + "first"][0], depth + 1))
            current = (cell.get(RDF + "rest") or [RDF + "nil"])[0]
            depth += 1
        return {"list": items}
    for key, word in ((OWL + "unionOf", "or"), (OWL + "intersectionOf", "and")):
        if key in props:
            return {"op": word, "items": _expr(props[key][0], depth + 1).get("list", [])}
    if OWL + "onProperty" in props:
        restriction = {"on": _expr(props[OWL + "onProperty"][0], depth + 1)}
        for key, word in ((OWL + "someValuesFrom", "some"), (OWL + "allValuesFrom", "only"), (OWL + "hasValue", "value"),
                          (OWL + "minCardinality", "min"), (OWL + "maxCardinality", "max"), (OWL + "cardinality", "exactly"),
                          (OWL + "qualifiedCardinality", "exactly"), (OWL + "minQualifiedCardinality", "min"),
                          (OWL + "maxQualifiedCardinality", "max")):
            if key in props:
                restriction["kind"] = word
                restriction["value"] = _expr(props[key][0], depth + 1)
        if OWL + "onClass" in props:
            restriction["class"] = _expr(props[OWL + "onClass"][0], depth + 1)
        return {"restriction": restriction}
    return {"text": "anonymous expression"}


def _values(values: list) -> list:
    return [_expr(v) for v in values]


def overview(module: str = "core") -> dict:
    """One module (core, requirements, workflow, software) or "all": metadata, counts, hierarchy, relations."""
    m = model()
    out, every = m["out"], m["terms"]
    terms = {i: t for i, t in every.items() if not t.get("reused") and (module == "all" or t["module"] == module)}
    head = out.get(MODULES["core" if module == "all" else module]["iri"], {})

    def meta(prop: str) -> str | None:
        v = head.get(prop, [])
        if not v:
            return None
        return v[0] if isinstance(v[0], str) else _text(v)

    counts = defaultdict(int)
    for t in terms.values():
        counts[t["kind"]] += 1
    used_ns = defaultdict(int)
    for s, props in out.items():
        for p, values in props.items():
            for iri in [s, p] + [v for v in values if isinstance(v, str)]:
                for ns in PREFIXES:
                    if iri.startswith(ns):
                        used_ns[ns] += 1

    # the class hierarchy of the module, from its classes without a parent in the module
    classes = {iri for iri, t in terms.items() if t["kind"] == "class"}
    all_classes = {iri for iri, t in every.items() if t["kind"] == "class"}

    def tree(iri: str, seen: frozenset) -> dict:
        kids = sorted((c for c in m["children"].get(iri, []) if c in classes and c not in seen), key=lambda c: terms[c]["label"].lower())
        return {**ref(iri), "instances": len(m["instances"].get(iri, [])),
                "children": [tree(c, seen | {c}) for c in kids]}

    roots = sorted((c for c in classes
                    if not any(p in classes for p in out.get(c, {}).get(RDFS + "subClassOf", []) if isinstance(p, str))),
                   key=lambda c: terms[c]["label"].lower())

    def total(node: dict) -> int:
        return node["instances"] + sum(total(c) for c in node["children"])

    hierarchy = [tree(r, frozenset({r})) for r in roots]
    for node in hierarchy:
        node["total"] = total(node)
        # the core's architecture: its four axes first, then the value sets ("descriptors")
        if node["module"] != "core":
            node["group"] = "extension"
        elif node["id"] in CORE_AXES:
            node["group"] = "axis"
        else:
            node["group"] = "descriptor"
    hierarchy.sort(key=lambda n: (n["group"] != "axis", CORE_AXES.index(n["id"]) if n["id"] in CORE_AXES else 0,
                                  n["group"] == "descriptor", n["label"].lower()))

    # the main relations: object properties of the module between AIO classes. In an
    # extension they often reach core classes: those are listed apart ("linked"), so the
    # diagram can show how the extension hangs on the core
    relations, linked = [], set()
    for iri, t in terms.items():
        if t["kind"] != "object":
            continue
        doms = [d for d in out.get(iri, {}).get(RDFS + "domain", []) if isinstance(d, str) and d in all_classes]
        rans = [r for r in out.get(iri, {}).get(RDFS + "range", []) if isinstance(r, str) and r in all_classes]
        for d in doms:
            for r in rans:
                if d in classes or r in classes:
                    relations.append({"property": ref(iri), "from": every[d]["id"], "to": every[r]["id"]})
                    linked |= {x for x in (d, r) if x not in classes}

    return {
        "module": module,
        "iri": MODULES["core" if module == "all" else module]["iri"],
        "title": meta(DCT + "title") or "AIO ontology",
        "description": meta(DCT + "description"),
        "version": meta(OWL + "versionInfo"),
        "version_iri": meta(OWL + "versionIRI"),
        "modified": meta(DCT + "modified"),
        "created": meta(DCT + "created"),
        "license": meta(DCT + "license"),
        "prefix": meta(VANN + "preferredNamespacePrefix") or "aio",
        "namespace": meta(VANN + "preferredNamespaceUri") or ONTOLOGY_NS,
        "imports": [v for v in head.get(OWL + "imports", []) if isinstance(v, str)],
        "counts": {"classes": counts["class"], "object_properties": counts["object"],
                   "datatype_properties": counts["datatype"], "annotation_properties": counts["annotation"],
                   "individuals": counts["individual"],
                   "triples": sum(len(v) for s, p in out.items() for v in p.values()
                                  if module == "all" or (s in terms) or (module_of(s) is None and module == "core"))},
        "namespaces": [{"prefix": PREFIXES[ns], "namespace": ns, "uses": n}
                       for ns, n in sorted(used_ns.items(), key=lambda x: (PREFIXES[x[0]] != "aio", -x[1]))],
        "hierarchy": hierarchy,
        "relations": relations,
        "linked": sorted((ref(c) for c in linked), key=lambda r: r["label"].lower()),
        "formats": [{"id": f, "media_type": t} for f, (t, _) in FORMATS.items()],
        "modules": modules(),
        "alignments": alignment_summary() if module in ("core", "all") else [],
        "reused": reused_summary() if module in ("core", "all") else [],
    }


def reused_summary() -> list[dict]:
    """The vocabularies AIO reuses, each with the terms it takes from them and how they are used."""
    m = model()
    groups: dict[str, dict] = {}
    for iri, t in m["terms"].items():
        if not t.get("reused"):
            continue
        short, name, url = reused_vocabulary(iri)
        group = groups.setdefault(short, {"vocabulary": short, "name": name, "url": url, "namespaces": set(),
                                          "terms": [], "uses": 0})
        group["namespaces"].add(next(ns for ns in REUSED if iri.startswith(ns)))
        group["uses"] += t["uses"]
        group["terms"].append({**ref(iri), "uses": t["uses"], "instances": len(m["instances"].get(iri, []))})
    order = {"class": 0, "object": 1, "datatype": 2, "annotation": 3, "individual": 4}
    for group in groups.values():
        group["namespaces"] = sorted(group["namespaces"])
        group["terms"].sort(key=lambda r: (order.get(r["kind"], 9), r["label"].lower()))
    return sorted(groups.values(), key=lambda g: -g["uses"])


def modules() -> list[dict]:
    """The ontology files loaded (owl:Ontology resources): the core and the modules importing it."""
    out = model()["out"]
    found = []
    keys = {spec["iri"]: key for key, spec in MODULES.items()}
    counts = defaultdict(lambda: defaultdict(int))
    for t in model()["terms"].values():
        counts[t["module"]][t["kind"]] += 1
    for iri, props in out.items():
        if OWL + "Ontology" not in props.get(RDF + "type", []):
            continue
        key = keys.get(iri, "alignments" if iri == ALIGNMENTS_IRI else None)
        found.append({
            "key": key, "name": MODULE_TITLES.get(key, "Alignments" if key == "alignments" else iri),
            "prefix": next((v["value"] for v in props.get(VANN + "preferredNamespacePrefix", []) if isinstance(v, dict)), None),
            "counts": dict(counts.get(key, {})),
            "iri": iri, "title": _text(props.get(DCT + "title", [])) or iri,
            "description": _text(props.get(DCT + "description", [])),
            "version": _text(props.get(OWL + "versionInfo", [])),
            "version_iri": next((v for v in props.get(OWL + "versionIRI", []) if isinstance(v, str)), None),
            "imports": [v for v in props.get(OWL + "imports", []) if isinstance(v, str)],
        })
    order = ["core", "requirements", "workflow", "software", "alignments"]
    return sorted(found, key=lambda m: (order.index(m["key"]) if m["key"] in order else 9, m["iri"]))


def alignment_summary() -> list[dict]:
    """Every mapping of an AIO term to an external term, grouped by external vocabulary."""
    names = {short: full for _, short, full in VOCABULARIES}
    groups: dict[str, dict] = {}
    for iri, t in model()["terms"].items():
        if t["kind"] == "individual" and not alignments_of(iri):
            continue
        for a in alignments_of(iri):
            vocabulary = a["target"]["vocabulary"]
            group = groups.setdefault(vocabulary, {"vocabulary": vocabulary, "name": names.get(vocabulary, vocabulary),
                                                   "relations": defaultdict(int), "pairs": []})
            group["relations"][a["relation"]] += 1
            group["pairs"].append({"term": ref(iri), "relation": a["relation"], "target": a["target"]})
    for group in groups.values():
        group["relations"] = dict(sorted(group["relations"].items(), key=lambda x: -x[1]))
        group["pairs"].sort(key=lambda p: p["term"]["label"].lower())
        group["count"] = len(group["pairs"])
    return sorted(groups.values(), key=lambda g: -g["count"])


def term_list(module: str = "all") -> list[dict]:
    """Every class and property of a module, for the browser's side list (individuals are listed per class)."""
    m = model()
    found = []
    for iri, t in m["terms"].items():
        if t["kind"] == "individual" or t.get("reused") or (module != "all" and t["module"] != module):
            continue
        prop = RDFS + "subClassOf" if t["kind"] == "class" else RDFS + "subPropertyOf"
        parent = next((p for p in m["out"][iri].get(prop, []) if isinstance(p, str) and p in m["terms"]), None)
        found.append({"id": t["id"], "label": t["label"], "kind": t["kind"], "module": t["module"],
                      "definition": t["definition"], "parent": m["terms"][parent]["id"] if parent else None,
                      "instances": len(m["instances"].get(iri, []))})
    return sorted(found, key=lambda t: t["label"].lower())


def search(text: str, limit: int = 60) -> list[dict]:
    """Terms (individuals included) whose label, id or definition contains every word."""
    words = text.lower().split()
    if not words:
        return []
    order = {"class": 0, "object": 1, "datatype": 2, "annotation": 3, "individual": 4}
    found = []
    for t in model()["terms"].values():
        name = f"{t['label']} {t['id']}".lower()
        whole = f"{name} {t['definition'] or ''}".lower()
        if all(w in whole for w in words):
            label = t["label"].lower()
            # exact name first, then names starting with the text, then names containing it, then definitions
            rank = 0 if label == text.lower().strip() or t["id"].lower() == text.lower().strip()                 else 1 if label.startswith(words[0]) or t["id"].lower().startswith(words[0])                 else 2 if all(w in name for w in words) else 3
            found.append((rank, order[t["kind"]], label, t))
    found.sort(key=lambda x: x[:3])
    return [{"id": t["id"], "label": t["label"], "kind": t["kind"], "definition": t["definition"], "module": t["module"]}
            for *_, t in found[:limit]]


def term(term_id: str) -> dict | None:
    m = model()
    iri = m["by_id"].get(term_id, ONTOLOGY_NS + term_id)
    t = m["terms"].get(iri)
    if t is None:
        return None
    out, incoming = m["out"], m["in"]
    props = out[iri]
    labels = [{"value": v["value"], "lang": v["lang"]} for v in props.get(RDFS + "label", []) if isinstance(v, dict)]
    result = {
        **ref(iri), "curie": curie(iri), "definition": t["definition"],
        "comment": _text(props.get(RDFS + "comment", [])),
        "labels": labels,
        "types": [ref(x) for x in props.get(RDF + "type", []) if isinstance(x, str)],
        "alignments": alignments_of(iri),
        "reused_from": None if not t.get("reused") else dict(zip(("vocabulary", "name", "url"), reused_vocabulary(iri))),
        "annotations": [
            {"property": ref(p), "values": [v if isinstance(v, dict) else ref(v) for v in values]}
            for p, values in sorted(props.items(), key=lambda x: curie(x[0]))
            if p not in SHOWN_APART and t["kind"] != "individual"
        ],
    }

    def refs(prop: str, source=props) -> list:
        return _values(source.get(prop, []))

    if t["kind"] == "class":
        supers = props.get(RDFS + "subClassOf", [])
        result.update({
            "superclasses": [_expr(s) for s in supers if isinstance(s, str)],
            "restrictions": [_expr(s) for s in supers if isinstance(s, dict)],
            "subclasses": sorted((ref(c) for c in m["children"].get(iri, [])), key=lambda r: r["label"].lower()),
            "equivalent": refs(OWL + "equivalentClass"),
            "disjoint": refs(OWL + "disjointWith"),
            "ancestors": _ancestors(iri, RDFS + "subClassOf"),
            "in_domain_of": sorted((ref(s) for s, p in incoming.get(iri, []) if p == RDFS + "domain" and s in m["terms"]),
                                   key=lambda r: r["label"].lower()),
            "in_range_of": sorted((ref(s) for s, p in incoming.get(iri, []) if p == RDFS + "range" and s in m["terms"]),
                                  key=lambda r: r["label"].lower()),
            "instances": sorted((ref(i) for i in m["instances"].get(iri, [])), key=lambda r: r["label"].lower()),
            "instances_total": _instances_below(iri),
        })
    elif t["kind"] in ("object", "datatype", "annotation"):
        result.update({
            "superproperties": refs(RDFS + "subPropertyOf"),
            "subproperties": sorted((ref(c) for c in m["children"].get(iri, [])), key=lambda r: r["label"].lower()),
            "domain": refs(RDFS + "domain"),
            "range": refs(RDFS + "range"),
            "inverse": refs(OWL + "inverseOf") + [ref(s) for s, p in incoming.get(iri, []) if p == OWL + "inverseOf"],
            "chains": refs(OWL + "propertyChainAxiom"),
            "disjoint": refs(OWL + "propertyDisjointWith"),
            "characteristics": [CHARACTERISTICS[x] for x in props.get(RDF + "type", []) if x in CHARACTERISTICS],
            "ancestors": _ancestors(iri, RDFS + "subPropertyOf"),
            "usage": _usage(iri),
        })
    else:
        grouped = []
        for p, values in sorted(props.items(), key=lambda x: (x[0] != SKOS + "definition", ref(x[0])["label"].lower())):
            if p in (RDF + "type", RDFS + "label", SKOS + "definition", RDFS + "comment"):
                continue
            grouped.append({"property": ref(p), "values": [v if isinstance(v, dict) and "value" in v else _expr(v) for v in values]})
        back = defaultdict(list)
        for s, p in incoming.get(iri, []):
            if not s.startswith("_:") and s in m["terms"]:
                back[p].append(ref(s))
        result.update({
            "classes": [ref(c) for c in t["types"]],
            "facts": grouped,
            "referenced_by": [{"property": ref(p), "subjects": sorted(v, key=lambda r: r["label"].lower())}
                              for p, v in sorted(back.items(), key=lambda x: ref(x[0])["label"].lower())],
        })
    return result


def _ancestors(iri: str, prop: str) -> list[list[dict]]:
    """Every path from the term up to a root (classes can have several parents)."""
    out, terms = model()["out"], model()["terms"]
    paths: list[list[dict]] = []

    def walk(node: str, path: list[str]) -> None:
        ups = [p for p in out.get(node, {}).get(prop, []) if isinstance(p, str) and p in terms and p not in path]
        if not ups:
            if path:
                paths.append([ref(x) for x in reversed(path)])
            return
        for up in ups:
            walk(up, path + [up])
        if len(paths) > 6:
            return

    walk(iri, [])
    return paths[:6]


def _instances_below(iri: str) -> int:
    m = model()
    seen, todo, n = set(), [iri], 0
    while todo:
        c = todo.pop()
        if c in seen:
            continue
        seen.add(c)
        n += len(m["instances"].get(c, []))
        todo += m["children"].get(c, [])
    return n


def _usage(prop: str, limit: int = 8) -> dict:
    """How often a property is used in the knowledge base, with a few examples."""
    examples, n = [], 0
    for s, props in model()["out"].items():
        if s.startswith("_:"):
            continue
        for v in props.get(prop, []):
            n += 1
            if len(examples) < limit and s in model()["terms"]:
                examples.append({"subject": ref(s), "object": v if isinstance(v, dict) and "value" in v else _expr(v)})
    return {"count": n, "examples": examples}


# ----------------------------------------------------------------------------
# Export
# ----------------------------------------------------------------------------

SCHEMA_QUERY = """PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
CONSTRUCT { ?s ?p ?o . ?b ?bp ?bo }
FROM <http://www.ontotext.com/explicit>
WHERE {
  ?s a ?t . VALUES ?t { owl:Ontology owl:Class owl:ObjectProperty owl:DatatypeProperty owl:AnnotationProperty }
  ?s ?p ?o .
  OPTIONAL {
    FILTER(isBlank(?o))
    ?o (rdf:first|rdf:rest|owl:unionOf|owl:intersectionOf|owl:onProperty|owl:someValuesFrom|owl:allValuesFrom|owl:onClass)* ?b .
    FILTER(isBlank(?b))
    ?b ?bp ?bo
  }
}"""


PARTS = ["schema", "all", *MODULES, "alignments"]


def export(fmt: str, part: str) -> tuple[bytes, str, str]:
    """Serialised by GraphDB: the schema of every module, everything, or one module (its graph)."""
    media_type, ext = FORMATS[fmt]
    repository = f"{GRAPHDB_URL}/repositories/{GRAPHDB_REPO}"
    graph = MODULES[part]["iri"] if part in MODULES else ALIGNMENTS_IRI if part == "alignments" else None
    with httpx.Client(timeout=120) as client:
        if part == "schema":
            response = client.post(repository, data={"query": SCHEMA_QUERY, "infer": "false"}, headers={"Accept": media_type})
        elif graph:
            response = client.get(f"{repository}/statements", params={"infer": "false", "context": f"<{graph}>"},
                                  headers={"Accept": media_type})
        else:
            response = client.get(f"{repository}/statements", params={"infer": "false"}, headers={"Accept": media_type})
    response.raise_for_status()
    version = overview("core")["version"] or "latest"
    return response.content, media_type, f"aio-{part}-{version}.{ext}"
