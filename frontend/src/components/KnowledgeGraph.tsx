import type { GraphNode, Workflow } from "../api";

// Which column each kind of node lives in (software and variables share one column).
const COLUMN_OF: Record<GraphNode["kind"], number> = {
  challenge: 0,
  process: 1,
  method: 2,
  software: 3,
  variable: 3,
  dataset: 4,
};
const ORDER: GraphNode["kind"][] = ["challenge", "process", "method", "software", "variable", "dataset"];

const COL_W = 200;   // width of one column
const NODE_W = 172;
const NODE_H = 28;
const ROW_H = 40;    // vertical space of one node
const PAD = 14;

const short = (text: string) => (text.length > 22 ? text.slice(0, 21) + "…" : text);

const LEGEND = [
  { css: "sw-challenge", text: "Challenge" },
  { css: "sw-process", text: "Process" },
  { css: "sw-method", text: "Method" },
  { css: "sw-software", text: "Software" },
  { css: "sw-have", text: "Data you have" },
  { css: "sw-miss", text: "Data missing" },
  { css: "sw-dataset", text: "Open dataset" },
];

export default function KnowledgeGraph({ graph }: { graph: Workflow }) {
  if (graph.nodes.length === 0) return null;

  // Columns actually used, left to right (an empty column is skipped, not left blank).
  const used = [...new Set(graph.nodes.map((n) => COLUMN_OF[n.kind]))].sort((a, b) => a - b);
  const columns: GraphNode[][] = used.map(() => []);
  for (const kind of ORDER) {
    for (const node of graph.nodes) {
      if (node.kind === kind) columns[used.indexOf(COLUMN_OF[kind])].push(node);
    }
  }

  const height = Math.max(...columns.map((c) => c.length)) * ROW_H + PAD * 2;
  const width = used.length * COL_W;

  // Position of every node: its column gives x, its rank in the column gives y (centred).
  const position = new Map<string, { x: number; y: number }>();
  columns.forEach((column, c) => {
    const top = (height - column.length * ROW_H) / 2 + (ROW_H - NODE_H) / 2;
    column.forEach((node, r) => {
      position.set(node.id, { x: c * COL_W + (COL_W - NODE_W) / 2, y: top + r * ROW_H });
    });
  });

  return (
    <>
      <svg className="graph" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Knowledge graph">
        {graph.edges.map((edge) => {
          const from = position.get(edge.source);
          const to = position.get(edge.target);
          if (!from || !to) return null;
          const x1 = from.x + NODE_W;
          const y1 = from.y + NODE_H / 2;
          const x2 = to.x;
          const y2 = to.y + NODE_H / 2;
          const mid = (x1 + x2) / 2;
          return (
            <path
              key={`${edge.source}>${edge.target}`}
              className="g-edge"
              d={`M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}`}
            />
          );
        })}

        {graph.nodes.map((node) => {
          const p = position.get(node.id)!;
          const css = `g-node g-${node.kind}${
            node.kind === "variable" ? (node.have ? " g-have" : " g-miss") : ""
          }`;
          return (
            <g key={node.id} className={css} transform={`translate(${p.x},${p.y})`}>
              <title>{node.label}</title>
              <rect width={NODE_W} height={NODE_H} rx={14} />
              <text x={NODE_W / 2} y={NODE_H / 2} textAnchor="middle" dominantBaseline="central">
                {short(node.label)}
              </text>
            </g>
          );
        })}
      </svg>

      <div className="legend">
        {LEGEND.map((item) => (
          <span key={item.css}>
            <span className={`swatch ${item.css}`}></span>
            {item.text}
          </span>
        ))}
      </div>
    </>
  );
}