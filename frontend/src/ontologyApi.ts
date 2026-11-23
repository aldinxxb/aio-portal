// The AIO ontology section: documentation and browser of the ontology itself.
const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export type Kind = "class" | "object" | "datatype" | "annotation" | "individual" | "external";
// the modules of AIO 0.9.0: a core and three extensions used by the recommendation
export type ModuleKey = "core" | "requirements" | "workflow" | "software";
export type View = ModuleKey | "all";
export type TermRef = { id: string; label: string; kind: Kind; iri: string; external: boolean; vocabulary?: string | null;
                        module?: ModuleKey | null; reused?: string };   // reused: the vocabulary it comes from (DCAT...)
// a vocabulary whose terms AIO reuses with their own IRI (dcat:Dataset...)
export type ReusedVocabulary = { vocabulary: string; name: string; url: string; namespaces: string[]; uses: number;
                                 terms: (TermRef & { uses: number; instances: number })[] };
// how an AIO term maps to a term of another vocabulary (module aio-alignments)
export type Alignment = { relation: string; target: TermRef };
// a class expression or value, as the backend writes it
export type Expr =
  | TermRef
  | { literal: string }
  | { list: Expr[] }
  | { op: "or" | "and"; items: Expr[] }
  | { restriction: { on: Expr; kind?: string; value?: Expr; class?: Expr } }
  | { text: string }
  | { value: string; lang: string | null; datatype: string | null };

export type TreeNode = TermRef & { instances: number; total?: number; children: TreeNode[]; group?: "axis" | "descriptor" | "extension" };

export type Overview = {
  module: View; imports: string[];
  linked: TermRef[];               // core classes an extension hangs on
  reused: ReusedVocabulary[];      // vocabularies AIO reuses terms from
  iri: string; title: string; description: string | null; version: string | null; version_iri: string | null;
  modified: string | null; created: string | null; license: string | null; prefix: string; namespace: string;
  counts: { classes: number; object_properties: number; datatype_properties: number; annotation_properties: number; individuals: number; triples: number };
  namespaces: { prefix: string; namespace: string; uses: number }[];
  hierarchy: TreeNode[];
  relations: { property: TermRef; from: string; to: string }[];
  formats: { id: string; media_type: string }[];
  modules: { key: ModuleKey | "alignments" | null; name: string; prefix: string | null; counts: Partial<Record<Kind, number>>;
             iri: string; title: string; description: string | null; version: string | null; version_iri: string | null; imports: string[] }[];
  alignments: { vocabulary: string; name: string; count: number; relations: Record<string, number>; pairs: { term: TermRef; relation: string; target: TermRef }[] }[];
};

export type ListedTerm = { id: string; label: string; kind: Kind; definition: string | null; parent: string | null; instances: number; module?: ModuleKey | null };

export type Term = TermRef & {
  curie: string; definition: string | null; comment: string | null;
  labels: { value: string; lang: string | null }[];
  types: TermRef[];
  annotations: { property: TermRef; values: Expr[] }[];
  alignments: Alignment[];
  reused_from: { vocabulary: string; name: string; url: string } | null;
  ancestors?: TermRef[][];
  // class
  superclasses?: Expr[]; restrictions?: Expr[]; subclasses?: TermRef[]; equivalent?: Expr[]; disjoint?: Expr[];
  in_domain_of?: TermRef[]; in_range_of?: TermRef[]; instances?: TermRef[]; instances_total?: number;
  // property
  superproperties?: Expr[]; subproperties?: TermRef[]; domain?: Expr[]; range?: Expr[]; inverse?: Expr[];
  chains?: Expr[]; characteristics?: string[];
  usage?: { count: number; examples: { subject: TermRef; object: Expr }[] };
  // individual
  classes?: TermRef[];
  facts?: { property: TermRef; values: Expr[] }[];
  referenced_by?: { property: TermRef; subjects: TermRef[] }[];
};

const kept = new Map<string, Promise<unknown>>();
function get<T>(path: string): Promise<T> {
  if (!kept.has(path)) {
    const asked = fetch(`${API_URL}${path}`).then((r) => {
      if (!r.ok) throw new Error(`${path}: error ${r.status}`);
      return r.json();
    });
    asked.catch(() => kept.delete(path));
    kept.set(path, asked);
  }
  return kept.get(path) as Promise<T>;
}

export const getOverview = (module: View = "core") => get<Overview>(`/ontology?module=${module}`);
export const getTerms = (module: View = "all") => get<ListedTerm[]>(`/ontology/terms?module=${module}`);
export const getTerm = (id: string) => get<Term>(`/ontology/${encodeURIComponent(id)}`);
export const searchTerms = (q: string) => get<ListedTerm[]>(`/ontology/search?q=${encodeURIComponent(q)}`);
export const exportUrl = (format: string, part: string) => `${API_URL}/ontology/export?format=${format}&part=${part}`;
