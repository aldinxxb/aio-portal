"""Run with:  pytest      (from the backend folder). Needs GraphDB running with the ontology loaded.

The AIO ontology section: documentation built from the asserted triples, and exports.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_overview_gives_metadata_counts_hierarchy_and_relations():
    found = client.get("/ontology").json()
    assert found["iri"] == "https://w3id.org/aio" and found["prefix"] == "aio" and found["version"]
    counts = found["counts"]
    assert counts["classes"] > 50 and counts["object_properties"] > 50 and counts["individuals"] > 100
    assert any(n["prefix"] == "aio" for n in found["namespaces"])
    # every class appears once in the hierarchy
    seen = []
    def walk(node):
        seen.append(node["id"])
        for child in node["children"]:
            walk(child)
    for root in found["hierarchy"]:
        walk(root)
    assert len(seen) == len(set(seen)) == counts["classes"]
    assert found["relations"] and all(r["property"]["kind"] == "object" for r in found["relations"])


def test_a_class_lists_its_hierarchy_properties_and_individuals():
    term = client.get("/ontology/WaterChallenge").json()
    assert term["kind"] == "class" and term["curie"] == "aio:WaterChallenge" and term["definition"]
    assert any(s["id"] == "ProblemDefinition" for s in term["superclasses"])
    assert any(p["id"] == "hasPrimaryProcess" for p in term["in_domain_of"])
    assert any(i["id"] == "Flood" for i in term["instances"])


def test_a_property_gives_domain_range_inverse_and_usage():
    term = client.get("/ontology/hasPrimaryProcess").json()
    assert term["kind"] == "object"
    assert [d["id"] for d in term["domain"]] == ["WaterChallenge"] and [r["id"] for r in term["range"]] == ["Process"]
    assert term["inverse"] and term["usage"]["count"] > 0


def test_an_individual_gives_its_facts_and_who_refers_to_it():
    term = client.get("/ontology/Flood").json()
    assert term["kind"] == "individual" and any(c["id"] == "WaterChallenge" for c in term["classes"])
    assert any(f["property"]["id"] == "hasPrimaryProcess" for f in term["facts"])
    assert term["referenced_by"]


def test_search_puts_the_exact_name_first():
    found = client.get("/ontology/search", params={"q": "flood"}).json()
    assert found[0]["id"] == "Flood"
    assert client.get("/ontology/search", params={"q": ""}).json() == []


def test_unknown_term_is_404():
    assert client.get("/ontology/NoSuchTerm").status_code == 404


def test_exports_in_every_format():
    for fmt, marker in (("ttl", b"@prefix"), ("rdf", b"rdf:RDF"), ("jsonld", b"@id"), ("nt", b"<https://w3id.org/aio")):
        response = client.get("/ontology/export", params={"format": fmt, "part": "schema"})
        assert response.status_code == 200, fmt
        assert marker in response.content[:5000] or marker in response.content, fmt
        assert "attachment" in response.headers["content-disposition"]
    assert client.get("/ontology/export", params={"format": "xls"}).status_code == 422


def test_alignments_module_is_documented():
    """The aio-alignments module (own graph in GraphDB): mappings to ENVO, SWEET, BFO..."""
    found = client.get("/ontology").json()
    assert any(m["iri"] == "https://w3id.org/aio/alignments" for m in found["modules"])
    vocabularies = {g["vocabulary"]: g for g in found["alignments"]}
    assert {"ENVO", "SWEET", "BFO"} <= set(vocabularies)
    assert all(p["target"]["external"] for g in found["alignments"] for p in g["pairs"])
    river = client.get("/ontology/River").json()
    assert any(a["relation"] == "exact match" and a["target"]["vocabulary"] == "ENVO" for a in river["alignments"])
    # an external term carries its own label, not its IRI
    assert all(not a["target"]["label"].startswith("http") for a in river["alignments"])


# ---- 0.9.0: a core and three extensions, each in its own namespace -------------------------
EXTENSIONS = {"requirements": "https://w3id.org/aio/requirements#", "workflow": "https://w3id.org/aio/workflow#",
              "software": "https://w3id.org/aio/software#"}


def test_the_core_shows_its_four_axes_first_and_no_extension_term():
    core = client.get("/ontology", params={"module": "core"}).json()
    groups = [h["group"] for h in core["hierarchy"]]
    assert [h["id"] for h in core["hierarchy"] if h["group"] == "axis"] == \
        ["ProblemDefinition", "WaterSystemDefinition", "ModelingDefinition", "DataRepresentation"]
    assert groups.index("descriptor") > groups.index("axis") and "extension" not in groups
    every = client.get("/ontology/terms", params={"module": "core"}).json()
    assert every and all(t["module"] == "core" for t in every)
    assert not {"ChainStep", "fillsRole", "Requirement"} & {t["id"] for t in every}


def test_each_extension_has_its_namespace_header_and_imports():
    modules = {m["key"]: m for m in client.get("/ontology").json()["modules"]}
    for key, ns in EXTENSIONS.items():
        view = client.get("/ontology", params={"module": key}).json()
        assert view["namespace"] == ns and view["version"] == "0.9.0"
        assert "https://w3id.org/aio" in view["imports"]
        assert modules[key]["counts"].get("class", 0) > 0
        assert all(t["module"] == key for t in client.get("/ontology/terms", params={"module": key}).json())
    # a moved term keeps its local name and lives in its extension's namespace
    term = client.get("/ontology/fillsRole").json()
    assert term["iri"] == EXTENSIONS["workflow"] + "fillsRole" and term["module"] == "workflow"
    assert [d["id"] for d in term["domain"]] == ["ModelingMethod"]


def test_the_core_never_refers_to_an_extension():
    from app.sparql_client import run_select
    rows = run_select("""SELECT (COUNT(*) AS ?n) WHERE { GRAPH <https://w3id.org/aio> { ?s ?p ?o }
      FILTER(isIRI(?o) && (STRSTARTS(STR(?o), "https://w3id.org/aio/requirements#") || STRSTARTS(STR(?o), "https://w3id.org/aio/workflow#")
             || STRSTARTS(STR(?o), "https://w3id.org/aio/software#")) && ?p != <http://purl.org/dc/terms/isReplacedBy>) }""")
    assert rows[0]["n"] == "0"


def test_a_module_can_be_downloaded_alone():
    response = client.get("/ontology/export", params={"format": "ttl", "part": "workflow"})
    assert response.status_code == 200 and b"workflow#" in response.content
    assert b"aio#ChainStep" not in response.content
    assert client.get("/ontology", params={"module": "nope"}).status_code == 422


def test_terms_reused_from_other_vocabularies_are_documented():
    """dcat:Dataset, foaf:Organization... are used with their own IRI: AIO says where they come from."""
    core = client.get("/ontology", params={"module": "core"}).json()
    vocabularies = {g["vocabulary"]: g for g in core["reused"]}
    assert {"DCAT", "DCTERMS", "FOAF", "QUDT", "SKOS"} <= set(vocabularies)
    assert any(t["id"] == "dcat:Dataset" and t["instances"] > 0 for t in vocabularies["DCAT"]["terms"])
    term = client.get("/ontology/dcat:Dataset").json()
    assert term["reused_from"]["vocabulary"] == "DCAT" and term["iri"] == "http://www.w3.org/ns/dcat#Dataset"
    assert term["instances"]
    # reused terms are not counted as AIO's own
    assert all(not t["id"].startswith(("dcat:", "dct:", "foaf:")) for t in client.get("/ontology/terms").json())
