import type { GraphNode, Workflow } from "../api";
import KnowledgeGraph from "./KnowledgeGraph";

// One row of the workflow table: a title and the kind of node it lists.
const ROWS: { title: string; kind: GraphNode["kind"] }[] = [
  { title: "Water challenge", kind: "challenge" },
  { title: "Main processes", kind: "process" },
  { title: "Methods", kind: "method" },
  { title: "Software", kind: "software" },
  { title: "Data", kind: "variable" },
  { title: "Open data", kind: "dataset" },
];

type Props = {
  graph: Workflow;
  scope: string;   // short text saying which methods the workflow is built from
};

export default function WorkflowSection({ graph, scope }: Props) {
  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2 className="panel-title">Recommended workflow</h2>
            <p className="panel-sub">Ontology path from challenge to processes, methods, software and data · {scope}</p>
          </div>
        </div>

        {ROWS.map((row) => {
          const items = graph.nodes.filter((n) => n.kind === row.kind);
          return (
            <div key={row.kind} className="flow-row">
              <div className="flow-title">{row.title}</div>
              <div className="pills">
                {items.length === 0 && <span className="muted">–</span>}
                {items.map((n) =>
                  row.kind === "variable" ? (
                    <span key={n.id} className={`pill${n.have ? "" : " pill-warn"}`}>
                      {n.have ? "✓" : "⚠"} {n.label}
                    </span>
                  ) : (
                    <span key={n.id} className="pill">
                      {n.label}
                    </span>
                  )
                )}
              </div>
            </div>
          );
        })}
      </section>

      <section className="panel">
        <div className="panel-head">
          <div>
            <h2 className="panel-title">Dynamic knowledge graph</h2>
            <p className="panel-sub">Relationships behind the recommendation, drawn from the ontology.</p>
          </div>
        </div>
        <KnowledgeGraph graph={graph} />
      </section>
    </>
  );
}