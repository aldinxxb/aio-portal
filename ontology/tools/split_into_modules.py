"""Split AIO 0.8.0 into a core ontology and three extension ontologies (AIO 0.9.0).

    aio:     https://w3id.org/aio#               core: the four axes and the descriptive value sets
    aioreq:  https://w3id.org/aio/requirements#  study requirements: rules a study implies
    aiowf:   https://w3id.org/aio/workflow#      model composition: roles, interfaces, templates, slots
    aiosw:   https://w3id.org/aio/software#      software implementations: modules, reference chains, steps

Moved terms keep their local name; only their namespace changes. The old IRIs stay known
through aio-deprecated.ttl (owl:deprecated + dct:isReplacedBy).

How it works (no RDF library needed: GraphDB parses and checks everything)
  1. the source files are loaded, each in its own graph, into a temporary GraphDB
     repository WITHOUT inference, and read back triple by triple;
  2. each triple goes to the module of the most specific term it uses (subject, predicate
     or object): a core method described with an extension property ("SCS-CN fills role
     excess rainfall") belongs to that extension, so the core never depends on one;
  3. the files are written as Turtle, then loaded into a second temporary repository and
     compared with the source, triple for triple (after renaming): nothing lost, nothing added
     but the module headers, rdfs:isDefinedBy links and the deprecation records.

Run (GraphDB on localhost:7200, from the repository root):
    backend/.venv/Scripts/python ontology/tools/split_into_modules.py <membership.json> <source dir> <output dir>
membership.json maps each moved IRI to req / wf / sw (computed from domains and ranges, see
the migration notes in ontology/README-modules.md).
"""
import json
import pathlib
import re
import sys
import uuid
from collections import defaultdict

import httpx

GRAPHDB = "http://localhost:7200"
CORE = "https://w3id.org/aio#"
MODULES = {
    "core": {"ns": CORE, "prefix": "aio", "iri": "https://w3id.org/aio", "file": "aio-core.ttl",
             "title": "AIO ontology - core",
             "description": "Core of the AIO ontology: the problem a user wants to solve (water challenge, objective, "
                            "expected output), the water system (water entities, processes, variables), the modelling "
                            "knowledge (methods, software platforms) and the representation of data (datasets, data "
                            "variables, provenance, derivations), with the value sets that describe them.",
             "imports": []},
    "req": {"ns": "https://w3id.org/aio/requirements#", "prefix": "aioreq", "iri": "https://w3id.org/aio/requirements",
            "file": "aio-requirements.ttl", "title": "AIO extension - study requirements",
            "description": "Rules that a study implies on the methods and data that can answer it (e.g. forecasting "
                           "requires continuous simulation), with their strength and weight. Used by the recommendation "
                           "to exclude or rank methods.",
            "imports": ["core"]},
    "wf": {"ns": "https://w3id.org/aio/workflow#", "prefix": "aiowf", "iri": "https://w3id.org/aio/workflow",
           "file": "aio-workflow.ttl", "title": "AIO extension - model composition",
           "description": "How methods are assembled into a model: the component roles a method can fill, the "
                          "interfaces through which roles exchange variables, chain templates and their slots, coupling "
                          "types. Used by the recommendation to build and check workflows.",
           "imports": ["core"]},
    "sw": {"ns": "https://w3id.org/aio/software#", "prefix": "aiosw", "iri": "https://w3id.org/aio/software",
           "file": "aio-software.ttl", "title": "AIO extension - software implementations",
           "description": "How methods are realised in software: software modules with their usual time step and "
                         "resolution, and curated reference chains (standard-practice workflows) with their steps.",
           "imports": ["core", "wf"]},
}
RANK = {"core": 0, "req": 1, "wf": 1, "sw": 2}
VERSION = "0.9.0"
MODIFIED = "2026-11-20"
LICENCE = "https://creativecommons.org/licenses/by/4.0/"

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
OWL = "http://www.w3.org/2002/07/owl#"
XSD = "http://www.w3.org/2001/XMLSchema#"
DCT = "http://purl.org/dc/terms/"
PREFIXES = {
    "rdf": RDF, "rdfs": RDFS, "owl": OWL, "xsd": XSD, "dct": DCT, "skos": "http://www.w3.org/2004/02/skos/core#",
    "vann": "http://purl.org/vocab/vann/", "dcat": "http://www.w3.org/ns/dcat#", "foaf": "http://xmlns.com/foaf/0.1/",
    "qudt": "http://qudt.org/schema/qudt/", "unit": "http://qudt.org/vocab/unit/", "geo": "http://www.opengis.net/ont/geosparql#",
    "obo": "http://purl.obolibrary.org/obo/", "iop": "https://w3id.org/iadopt/ont/", "sosa": "http://www.w3.org/ns/sosa/",
    "schema": "https://schema.org/",
}
for spec in MODULES.values():
    PREFIXES[spec["prefix"]] = spec["ns"]


# ---------------------------------------------------------------------------------------------
# GraphDB: a throw-away repository without inference, to parse and to compare
# ---------------------------------------------------------------------------------------------

CONFIG = """@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#>.
@prefix rep: <http://www.openrdf.org/config/repository#>.
@prefix sr: <http://www.openrdf.org/config/repository/sail#>.
@prefix sail: <http://www.openrdf.org/config/sail#>.
@prefix graphdb: <http://www.ontotext.com/config/graphdb#>.
[] a rep:Repository ; rep:repositoryID "{id}" ; rdfs:label "temporary, for the AIO module split" ;
   rep:repositoryImpl [ rep:repositoryType "graphdb:SailRepository" ;
     sr:sailImpl [ sail:sailType "graphdb:Sail" ; graphdb:ruleset "empty" ; graphdb:enable-context-index "true" ] ] .
"""


class Scratch:
    def __init__(self):
        self.id = "aio-split-" + uuid.uuid4().hex[:8]
        self.client = httpx.Client(timeout=300)

    def __enter__(self):
        r = self.client.post(f"{GRAPHDB}/rest/repositories", files={"config": ("c.ttl", CONFIG.format(id=self.id), "text/turtle")})
        r.raise_for_status()
        return self

    def __exit__(self, *exc):
        self.client.delete(f"{GRAPHDB}/rest/repositories/{self.id}")

    def load(self, path: pathlib.Path, graph: str) -> None:
        r = self.client.post(f"{GRAPHDB}/repositories/{self.id}/rdf-graphs/service", params={"graph": graph},
                             content=path.read_bytes(), headers={"Content-Type": "text/turtle"})
        if r.status_code >= 300:
            raise SystemExit(f"GraphDB could not parse {path.name}: {r.text[:500]}")

    def triples(self) -> list[tuple]:
        query = """SELECT ?g ?s ?p ?o ?st ?ot ?lang ?dt WHERE { GRAPH ?g { ?s ?p ?o }
          BIND(IF(isBlank(?s), "b", "i") AS ?st) BIND(IF(isBlank(?o), "b", IF(isIRI(?o), "i", "l")) AS ?ot)
          BIND(LANG(?o) AS ?lang) BIND(IF(isLiteral(?o), STR(DATATYPE(?o)), "") AS ?dt) }"""
        r = self.client.post(f"{GRAPHDB}/repositories/{self.id}", data={"query": query},
                             headers={"Accept": "application/sparql-results+json"})
        r.raise_for_status()
        rows = []
        for b in r.json()["results"]["bindings"]:
            v = {k: x["value"] for k, x in b.items()}
            s = ("_:" + v["s"]) if v["st"] == "b" else v["s"]
            if v["ot"] == "b":
                o = ("b", "_:" + v["o"])
            elif v["ot"] == "i":
                o = ("i", v["o"])
            else:
                dt = v.get("dt") or ""
                if dt in (XSD + "string", RDF + "langString"):
                    dt = ""
                o = ("l", v["o"], v.get("lang") or "", dt)
            rows.append((v["g"], s, v["p"], o))
        return rows


# ---------------------------------------------------------------------------------------------
# Renaming and assignment
# ---------------------------------------------------------------------------------------------

def renamer(membership: dict[str, str]):
    table = {old: MODULES[mod]["ns"] + old[len(CORE):] for old, mod in membership.items()}
    return table, (lambda iri: table.get(iri, iri))


def module_of_iri(iri: str) -> str:
    for mod, spec in MODULES.items():
        if mod != "core" and iri.startswith(spec["ns"]):
            return mod
    return "core"


def assign(triples: list[tuple]) -> dict:
    """Module of each (renamed) triple: the most specific module among its terms. A blank node
    goes with the triple that points to it (unions, property chains, lists)."""
    by_subject = defaultdict(list)
    for t in triples:
        by_subject[t[1]].append(t)
    result = {}

    def own(t) -> str:
        terms = [t[1], t[2]] + ([t[3][1]] if t[3][0] == "i" else [])
        return max((module_of_iri(x) for x in terms if not x.startswith("_:")), key=RANK.get, default="core")

    def follow(bnode: str, mod: str, seen: set) -> None:
        for t in by_subject.get(bnode, []):
            if id(t) in seen:
                continue
            seen.add(id(t))
            result[id(t)] = max(mod, own(t), key=RANK.get)
            if t[3][0] == "b":
                follow(t[3][1], result[id(t)], seen)

    for t in triples:
        if t[1].startswith("_:"):
            continue
        result[id(t)] = own(t)
    seen: set = set()
    for t in triples:
        if not t[1].startswith("_:") and t[3][0] == "b":
            follow(t[3][1], result[id(t)], seen)
    # stand-alone axioms ([ a owl:AllDisjointClasses ; owl:members (...) ]): a blank node that
    # nothing points to goes to the most specific module among all the terms it mentions
    pointed = {t[3][1] for t in triples if t[3][0] == "b"}
    for root in [s for s in by_subject if s.startswith("_:") and s not in pointed]:
        terms, todo, visited = set(), [root], set()
        while todo:
            node = todo.pop()
            if node in visited:
                continue
            visited.add(node)
            for t in by_subject.get(node, []):
                terms.add(t[2])
                if t[3][0] == "i":
                    terms.add(t[3][1])
                elif t[3][0] == "b":
                    todo.append(t[3][1])
        mod = max((module_of_iri(x) for x in terms), key=RANK.get, default="core")
        follow(root, mod, seen)
    missing = [t for t in triples if id(t) not in result]
    if missing:
        raise SystemExit(f"{len(missing)} blank-node triples are not reachable from a named term")
    return result


# ---------------------------------------------------------------------------------------------
# Turtle writer
# ---------------------------------------------------------------------------------------------

def short(iri: str) -> str:
    for prefix, ns in sorted(PREFIXES.items(), key=lambda x: -len(x[1])):
        if iri.startswith(ns):
            rest = iri[len(ns):]
            if rest and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_\-]*", rest) and not rest.endswith("-"):
                return f"{prefix}:{rest}"
    return f"<{iri}>"


def literal(value: str, lang: str, dt: str) -> str:
    text = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    if lang:
        return f'"{text}"@{lang}'
    if dt:
        return f'"{text}"^^{short(dt)}'
    return f'"{text}"'


def term(o) -> str:
    if o[0] == "i":
        return short(o[1])
    if o[0] == "b":
        return o[1]
    return literal(o[1], o[2], o[3])


ORDER = [OWL + "Ontology", OWL + "AnnotationProperty", OWL + "ObjectProperty", OWL + "DatatypeProperty", OWL + "Class"]
SECTIONS = {OWL + "Ontology": None, OWL + "AnnotationProperty": "Annotation properties", OWL + "ObjectProperty": "Object properties",
            OWL + "DatatypeProperty": "Data properties", OWL + "Class": "Classes"}


def write(path: pathlib.Path, triples: list[tuple], header_comment: str) -> None:
    subjects: dict[str, list] = defaultdict(list)
    for t in triples:
        subjects[t[1]].append(t)
    used = {p for t in triples for p in [t[1], t[2]] + ([t[3][1]] if t[3][0] == "i" else []) + ([t[3][3]] if t[3][0] == "l" and t[3][3] else [])}

    def kind(s: str) -> int:
        types = {t[3][1] for t in subjects[s] if t[2] == RDF + "type" and t[3][0] == "i"}
        for i, k in enumerate(ORDER):
            if k in types:
                return i
        return len(ORDER) + (1 if s.startswith("_:") else 0)

    lines = [f"@prefix {p}: <{ns}> ." for p, ns in sorted(PREFIXES.items()) if any(x.startswith(ns) for x in used)]
    lines += ["", header_comment, ""]
    current = None
    for s in sorted(subjects, key=lambda s: (kind(s), s.startswith("_:"), s.lower())):
        k = kind(s)
        title = SECTIONS.get(ORDER[k]) if k < len(ORDER) else ("Individuals" if not s.startswith("_:") else "Anonymous expressions")
        if title != current and title:
            lines += ["#################################################################", f"#    {title}",
                      "#################################################################", ""]
            current = title
        if not s.startswith("_:"):
            lines.append(f"###  {s}")
        preds: dict[str, list] = defaultdict(list)
        for t in subjects[s]:
            preds[t[2]].append(t[3])
        order = sorted(preds, key=lambda p: (p != RDF + "type", short(p)))
        body = []
        for p in order:
            objs = sorted({term(o) for o in preds[p]})
            body.append(f"{'a' if p == RDF + 'type' else short(p)} " + " ,\n        ".join(objs))
        lines.append((s if s.startswith("_:") else short(s)) + " " + " ;\n    ".join(body) + " .")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------------------------

def lit(text: str, lang: str = "en") -> tuple:
    return ("l", text, lang, "")


def main(membership_file: str, source: str, target: str) -> None:
    membership = json.loads(pathlib.Path(membership_file).read_text(encoding="utf-8"))
    src, dst = pathlib.Path(source), pathlib.Path(target)
    dst.mkdir(parents=True, exist_ok=True)
    table, rename = renamer(membership)
    files = {"core": "aio-core.ttl", "additions": "aio-additions.ttl", "software": "aio-software.ttl", "alignments": "aio-alignments.ttl"}

    with Scratch() as scratch:
        for name, file in files.items():
            scratch.load(src / file, f"urn:source:{name}")
        raw = scratch.triples()
    print("source triples:", len(raw), {name: sum(1 for t in raw if t[0] == f"urn:source:{name}") for name in files})

    # rename every IRI of a moved term (subject, predicate, object)
    def ren(t):
        g, s, p, o = t
        return (g, rename(s), rename(p), ("i", rename(o[1])) if o[0] == "i" else o)

    triples = [ren(t) for t in raw]
    where = assign(triples)

    # outputs: the alignments file keeps its own module; the drafts file keeps its core part
    out: dict[str, list] = defaultdict(list)
    for t in triples:
        origin = t[0].split(":")[-1]
        mod = where[id(t)]
        if origin == "alignments":
            out["alignments"].append(t)
        elif origin in ("additions", "software") and mod == "core":
            out["additions"].append(t)           # drafts about core terms (incl. the generator's corrections)
        elif origin == "software":
            out["generated"].append(t)           # what build_software_ttl.py writes
        else:
            out[mod].append(t)
    # the old core ontology header becomes the core header of 0.9.0
    out["core"] = [t for t in out["core"] if t[1] != MODULES["core"]["iri"]]

    added: dict[str, list] = defaultdict(list)
    for mod, spec in MODULES.items():
        s = spec["iri"]
        header = [(s, RDF + "type", ("i", OWL + "Ontology")), (s, OWL + "versionIRI", ("i", f"{s}/{VERSION}")),
                  (s, OWL + "versionInfo", ("l", VERSION, "", "")), (s, DCT + "title", lit(spec["title"])),
                  (s, DCT + "description", lit(spec["description"])), (s, DCT + "license", ("i", LICENCE)),
                  (s, DCT + "modified", ("l", MODIFIED, "", XSD + "date")),
                  (s, "http://purl.org/vocab/vann/preferredNamespacePrefix", ("l", spec["prefix"], "", "")),
                  (s, "http://purl.org/vocab/vann/preferredNamespaceUri", ("l", spec["ns"], "", ""))]
        header += [(s, OWL + "imports", ("i", MODULES[i]["iri"])) for i in spec["imports"]]
        if mod == "core":
            header.append((s, OWL + "priorVersion", ("i", "https://w3id.org/aio/0.8.0")))
        # every class and property says which module defines it
        declared = {t[1] for t in out[mod] + (out["generated"] if mod == "sw" else []) if t[2] == RDF + "type" and t[3][0] == "i"
                    and t[3][1] in (OWL + "Class", OWL + "ObjectProperty", OWL + "DatatypeProperty", OWL + "AnnotationProperty")
                    and t[1].startswith(spec["ns"])}
        header += [(d, RDFS + "isDefinedBy", ("i", s)) for d in sorted(declared)]
        added[mod] = [("urn:added", a, b, c) for a, b, c in header]
        out[mod] = added[mod] + out[mod]
    deprecated = []
    for old, new in sorted(table.items()):
        deprecated += [("urn:added", old, OWL + "deprecated", ("l", "true", "", XSD + "boolean")),
                       ("urn:added", old, DCT + "isReplacedBy", ("i", new))]
    out["deprecated"] = deprecated

    print("generator output by module:", {m: sum(1 for t in triples if t[0].endswith("software") and where[id(t)] == m) for m in MODULES})
    names = {"core": "aio-core.ttl", "req": "aio-requirements.ttl", "wf": "aio-workflow.ttl", "sw": "aio-software.ttl",
             "generated": "aio-software-generated.ttl",
             "additions": "aio-additions.ttl", "alignments": "aio-alignments.ttl", "deprecated": "aio-deprecated.ttl"}
    notes = {
        "core": "#  AIO core ontology " + VERSION + ". Generated by ontology/tools/split_into_modules.py from AIO 0.8.0;\n#  edit it in Protege like any ontology file.",
        "req": "#  AIO extension: study requirements " + VERSION + ". Imports the core.",
        "wf": "#  AIO extension: model composition " + VERSION + ". Imports the core.",
        "sw": "#  AIO extension: software implementations " + VERSION + ". Imports the core and model composition.\n"
              "#  More modules and workflows are generated into aio-software-generated.ttl by build_software_ttl.py.",
        "generated": "#  Software modules and extra reference workflows - DRAFT FOR EXPERT VALIDATION.\n"
                     "#  Generated by ontology/build_software_ttl.py: edit the tables there, not this file.\n"
                     "#  Part of the extension https://w3id.org/aio/software (no ontology header of its own).",
        "additions": "#  Proposed additions to the AIO core - DRAFT FOR EXPERT VALIDATION.\n#  Once validated, merge these triples into aio-core.ttl and delete this file.",
        "alignments": "#  Alignments of AIO terms to external vocabularies (BFO, RO, SOSA, I-ADOPT, schema.org, ENVO, SWEET).",
        "deprecated": "#  IRIs of AIO 0.8.0 that moved to an extension in " + VERSION + ": each is replaced by the same\n#  local name in the extension's namespace.",
    }
    for key, file in names.items():
        write(dst / file, out[key], notes[key])
        print(f"{file:26s} {len(out[key]):6d} triples")

    # ---- proof: parse the output and compare with the renamed source, triple for triple ----
    with Scratch() as scratch:
        for key, file in names.items():
            scratch.load(dst / file, f"urn:out:{key}")
        back = scratch.triples()

    def norm(rows, skip_graph):
        named, blank = set(), defaultdict(int)
        for g, s, p, o in rows:
            if g in skip_graph:
                continue
            if s.startswith("_:") or o[0] == "b":
                blank[(p, o[0] if o[0] == "b" else term(o)) if s.startswith("_:") else (s, p)] += 1
            else:
                named.add((s, p, o))
        return named, dict(blank)

    expected = [t for t in triples if t[1] != MODULES["core"]["iri"]] + [t for mod in added for t in added[mod]] + deprecated
    exp_named, exp_blank = norm(expected, set())
    got_named, got_blank = norm(back, set())
    missing, extra = exp_named - got_named, got_named - exp_named
    print("check: named triples expected", len(exp_named), "written", len(got_named),
          "| missing", len(missing), "| extra", len(extra), "| blank-node patterns equal:", exp_blank == got_blank)
    for t in list(missing)[:5] + list(extra)[:5]:
        print("   ", t)
    if missing or extra or exp_blank != got_blank:
        raise SystemExit("MISMATCH: the output is not the renamed source")
    # the core must not depend on an extension
    core_refs = {x for t in out["core"] + out["additions"] for x in [t[1], t[2]] + ([t[3][1]] if t[3][0] == "i" else [])
                 if module_of_iri(x) != "core" and not x.startswith("_:")}
    print("extension terms referenced by the core:", sorted(core_refs)[:10] or "none")
    if core_refs:
        raise SystemExit("the core references extension terms")
    print("OK")


if __name__ == "__main__":
    main(*sys.argv[1:4])
