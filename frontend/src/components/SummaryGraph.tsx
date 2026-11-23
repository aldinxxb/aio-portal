import { useState } from "react";
import type { Chain, Recommendation, Ref } from "../api";

// A dynamic summary of the recommendation, drawn as a graph:
//
//   water challenge → processes concerned → workflows → expected outputs
//                                              ↓
//                                       data they require
//
// Every group can be opened: "7 possible workflows" opens into the workflows, a workflow
// focuses the graph on it alone (with a way back), "24 data variables" opens into forcing /
// boundary conditions / static description / initial state, and each of these into its
// variables. Clicking a workflow also tells the page, so the open data layer follows it.

const name = (item: Ref) => item.label ?? item.id;
const short = (text: string, max = 24) => (text.length > max ? text.slice(0, max - 1) + "…" : text);

type Nature = "forcing" | "boundary" | "static" | "initial";
const NATURES: { id: Nature; title: string }[] = [
  { id: "forcing", title: "Forcing" },
  { id: "boundary", title: "Boundary conditions" },
  { id: "static", title: "Static description" },
  { id: "initial", title: "Initial state" },
];
type State = "have" | "open_data" | "missing" | "initial";
const RANK: Record<State, number> = { have: 0, open_data: 1, initial: 2, missing: 3 };

type Kind = "challenge" | "process" | "workflows" | "workflow" | "output" | "data" | "nature" | "variable";
type Node = {
  key: string;
  kind: Kind;
  title: string;
  sub?: string;
  tone?: "ok" | "open" | "bad" | "main" | "plain";
  action?: () => void;
  hint: string;
  x: number;
  y: number;
  w: number;
};
type Edge = { from: string; to: string };

const H = 38;           // node height
const GAP = 10;         // vertical gap in a column
const COLUMNS = [{ x: 0, w: 150 }, { x: 186, w: 170 }, { x: 394, w: 210 }, { x: 642, w: 178 }];
const WIDTH = 820;

type Props = {
  result: Recommendation;
  chains: Chain[];
  focus: string | null;                    // the workflow the graph is focused on
  onFocus: (id: string | null) => void;
  challenge: string;                       // the challenge, readable
};

type Needed = { ref: Ref; nature: Nature; state: State; by: Set<string> };

// Every variable the workflows require, once, with the best state found (you have it >
// open data > warm-up > no source) and the workflows needing it.
function requiredData(shown: Chain[]): Map<string, Needed> {
  const found = new Map<string, Needed>();
  const rows: { ref: Ref; nature: Nature; state: State; chain: string }[] = [];
  for (const c of shown) {
    for (const i of c.inputs) {
      rows.push({ ref: i, nature: (i.nature ?? (i.kind === "parameter" ? "static" : "forcing")) as Nature,
                  state: i.state as State, chain: c.id });
    }
    for (const i of c.initial_conditions) rows.push({ ref: i, nature: "initial", state: "initial", chain: c.id });
  }
  for (const row of rows) {
    const known = found.get(row.ref.id);
    const by = new Set([...(known?.by ?? []), row.chain]);
    const state = known && RANK[known.state] <= RANK[row.state] ? known.state : row.state;
    found.set(row.ref.id, { ref: row.ref, nature: known?.nature ?? row.nature, state, by });
  }
  return found;
}

export default function SummaryGraph({ result, chains, focus, onFocus, challenge }: Props) {
  const [openWorkflows, setOpenWorkflows] = useState(false);
  const [openData, setOpenData] = useState(false);
  const [openNature, setOpenNature] = useState<Nature | null>(null);
  const [hover, setHover] = useState<string | null>(null);

  const focused = chains.find((c) => c.id === focus) ?? null;
  const shown = focused ? [focused] : chains;
  const individual = focused !== null || openWorkflows;

  // ---- the data the shown workflows require, each variable once (best state wins) ------------
  const variables = requiredData(shown);
  const byNature = (n: Nature) => [...variables.values()].filter((v) => v.nature === n);

  // ---- the outputs: the ones chosen, else those the shown workflows deliver ----------------------
  const outputs: Ref[] = result.expected_outputs.length
    ? result.expected_outputs
    : [...new Map(shown.flatMap((c) => c.delivers).map((o) => [o.id, o])).values()];

  // ---- nodes, column by column -------------------------------------------------------------------
  const nodes: Omit<Node, "x" | "y" | "w">[][] = [[], [], [], []];
  const edges: Edge[] = [];
  nodes[0].push({ key: "challenge", kind: "challenge", title: challenge, sub: "water challenge", tone: "main", hint: "The water challenge of your study" });

  const processes = result.related_processes.values;
  for (const p of processes) {
    const main = result.related_processes.primary.includes(p.id);
    nodes[1].push({ key: `p:${p.id}`, kind: "process", title: name(p), sub: main ? "main process" : "process", tone: main ? "main" : "plain",
                    hint: main ? "A main process of the challenge" : "A process concerned by your study" });
    edges.push({ from: "challenge", to: `p:${p.id}` });
  }

  if (!individual) {
    const ready = chains.filter((c) => c.status === "runnable").length;
    nodes[2].push({ key: "w:all", kind: "workflows", title: `${chains.length} possible workflow${chains.length > 1 ? "s" : ""}`,
                    sub: `${ready} ready to run · click to open`, tone: "ok", action: () => setOpenWorkflows(true),
                    hint: "Click to see each workflow" });
    for (const p of processes) if (chains.some((c) => c.covers.some((x) => x.id === p.id))) edges.push({ from: `p:${p.id}`, to: "w:all" });
  } else {
    for (const c of shown) {
      const software = c.software.map(name).join(" + ");
      nodes[2].push({ key: `w:${c.id}`, kind: "workflow", title: c.label, sub: `${software} · ${c.status === "runnable" ? "ready" : "to check"}`,
                      tone: c.status === "runnable" ? "ok" : "bad", action: () => onFocus(focus === c.id ? null : c.id),
                      hint: `${c.label} · ${focus === c.id ? "click to see all the workflows again" : "click to focus on this workflow"}` });
      for (const p of processes) if (c.covers.some((x) => x.id === p.id)) edges.push({ from: `p:${p.id}`, to: `w:${c.id}` });
    }
  }

  for (const o of outputs) {
    const delivered = shown.some((c) => c.delivers.some((d) => d.id === o.id));
    nodes[3].push({ key: `o:${o.id}`, kind: "output", title: name(o), sub: delivered ? "expected output" : "not delivered",
                    tone: delivered ? "ok" : "bad", hint: delivered ? "Delivered by the workflows linked to it" : "No workflow shown delivers it" });
    if (!individual) { if (delivered) edges.push({ from: "w:all", to: `o:${o.id}` }); }
    else for (const c of shown) if (c.delivers.some((d) => d.id === o.id)) edges.push({ from: `w:${c.id}`, to: `o:${o.id}` });
  }

  // ---- data band, under the workflows ------------------------------------------------------------
  const band: Omit<Node, "x" | "y" | "w">[][] = [];
  const workflowKeys = individual ? shown.map((c) => `w:${c.id}`) : ["w:all"];
  if (!openData) {
    const missing = [...variables.values()].filter((v) => v.state === "missing").length;
    band.push([{ key: "d:all", kind: "data", title: `${variables.size} data variable${variables.size > 1 ? "s" : ""} required`,
                 sub: missing ? `${missing} without a source · click to open` : "click to open by kind", tone: missing ? "bad" : "open",
                 action: () => setOpenData(true), hint: "Click to see them by kind" }]);
    workflowKeys.forEach((w) => edges.push({ from: w, to: "d:all" }));
  } else {
    const row: Omit<Node, "x" | "y" | "w">[] = [];
    for (const n of NATURES) {
      const items = byNature(n.id);
      if (!items.length) continue;
      const missing = items.filter((v) => v.state === "missing").length;
      row.push({ key: `n:${n.id}`, kind: "nature", title: `${n.title} (${items.length})`, sub: openNature === n.id ? "click to close" : "click to see them",
                 tone: missing ? "bad" : "open", action: () => setOpenNature(openNature === n.id ? null : n.id),
                 hint: items.map((v) => name(v.ref)).join(", ") });
      for (const c of shown) if (items.some((v) => v.by.has(c.id))) edges.push({ from: individual ? `w:${c.id}` : "w:all", to: `n:${n.id}` });
    }
    band.push(row);
    if (openNature) {
      const items = byNature(openNature).sort((a, b) => RANK[b.state] - RANK[a.state]);
      const variablesRow = items.map((v) => ({
        key: `v:${v.ref.id}`, kind: "variable" as Kind, title: name(v.ref),
        sub: v.state === "have" ? "you have it" : v.state === "open_data" ? "open data" : v.state === "initial" ? "warm-up run" : "no source",
        tone: (v.state === "have" ? "ok" : v.state === "missing" ? "bad" : "open") as Node["tone"],
        hint: `needed by ${[...v.by].length} workflow(s)`,
      }));
      for (let i = 0; i < variablesRow.length; i += 4) band.push(variablesRow.slice(i, i + 4));
      variablesRow.forEach((v) => edges.push({ from: `n:${openNature}`, to: v.key }));
    }
  }

  // ---- positions ---------------------------------------------------------------------------------
  const heights = nodes.map((col) => col.length * H + Math.max(0, col.length - 1) * GAP);
  const top = Math.max(...heights, H) + 28;
  const laid: Node[] = [];
  nodes.forEach((col, c) => {
    const start = 26 + (top - 26 - heights[c]) / 2;
    col.forEach((n, i) => laid.push({ ...n, x: COLUMNS[c].x, y: start + i * (H + GAP), w: COLUMNS[c].w }));
  });
  let y = top + 34;
  for (const row of band) {
    const w = 190;
    const gap = 10;
    const total = row.length * w + (row.length - 1) * gap;
    const x0 = Math.max(0, Math.min(WIDTH - total, COLUMNS[2].x + COLUMNS[2].w / 2 - total / 2));
    row.forEach((n, i) => laid.push({ ...n, x: x0 + i * (w + gap), y, w }));
    y += H + 18;
  }
  const height = y + 4;
  const at = new Map(laid.map((n) => [n.key, n]));
  const lit = new Set<string>();
  if (hover) {
    lit.add(hover);
    for (const e of edges) {
      if (e.from === hover) lit.add(e.to);
      if (e.to === hover) lit.add(e.from);
    }
  }

  function path(e: Edge): string {
    const a = at.get(e.from)!;
    const b = at.get(e.to)!;
    if (b.y > a.y + H + 4 && Math.abs(b.y - a.y) > H) {          // down into the data band
      const x1 = a.x + a.w / 2, y1 = a.y + H, x2 = b.x + b.w / 2, y2 = b.y;
      return `M${x1},${y1} C${x1},${(y1 + y2) / 2} ${x2},${(y1 + y2) / 2} ${x2},${y2 - 3}`;
    }
    const x1 = a.x + a.w, y1 = a.y + H / 2, x2 = b.x - 3, y2 = b.y + H / 2, mid = (x1 + x2) / 2;
    return `M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}`;
  }

  return (
    <section className="panel summary-graph">
      <div className="panel-head">
        <div>
          <h2 className="panel-title">Summary of the recommendation</h2>
          <p className="panel-sub">
            From your challenge to the workflows, the data they require and the outputs they give.
            Click a box with a ▸ to open it.
          </p>
        </div>
        <div className="sg-tools">
          {focused && <button className="btn" onClick={() => onFocus(null)}>All workflows</button>}
          {!focused && openWorkflows && <button className="btn" onClick={() => setOpenWorkflows(false)}>Group the workflows</button>}
          {openData && <button className="btn" onClick={() => { setOpenData(false); setOpenNature(null); }}>Group the data</button>}
        </div>
      </div>
      {chains.length === 0 ? (
        <p className="muted">No workflow to summarise yet.</p>
      ) : (
        <div className="sg-layout">
        <div className="sg-canvas">
        <svg viewBox={`-2 0 ${WIDTH + 4} ${height}`} className="sg-svg" role="img" aria-label="Summary of the recommendation">
          <defs>
            <marker id="sg-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
              <path d="M0,0 L8,4 L0,8 z" className="sg-arrow" />
            </marker>
          </defs>
          {["Water challenge", "Processes concerned", focused ? "Workflow" : "Workflows", "Expected outputs"].map((t, i) => (
            <text key={t} x={COLUMNS[i].x + COLUMNS[i].w / 2} y={13} textAnchor="middle" className="sg-column">{t}</text>
          ))}
          <text x={COLUMNS[2].x + COLUMNS[2].w / 2} y={top + 24} textAnchor="middle" className="sg-column">Data required</text>
          {edges.filter((e) => at.has(e.from) && at.has(e.to)).map((e) => (
            <path key={`${e.from}>${e.to}`} d={path(e)} markerEnd="url(#sg-arrow)"
                  className={`sg-edge${hover && !(lit.has(e.from) && lit.has(e.to) && (e.from === hover || e.to === hover)) ? " dim" : ""}`} />
          ))}
          {laid.map((n) => (
            <g key={n.key} transform={`translate(${n.x},${n.y})`}
               className={`sg-node sg-${n.kind} sg-${n.tone ?? "plain"}${n.action ? " clickable" : ""}${hover && !lit.has(n.key) ? " dim" : ""}${focus && n.key === `w:${focus}` ? " focused" : ""}`}
               onMouseEnter={() => setHover(n.key)} onMouseLeave={() => setHover(null)}
               onClick={() => n.action?.()}>
              <title>{n.hint}</title>
              <rect width={n.w} height={H} rx={9} />
              <text x={10} y={16} className="sg-title">{n.action ? "▸ " : ""}{short(n.title, Math.floor(n.w / 7.2))}</text>
              {n.sub && <text x={10} y={30} className="sg-sub">{short(n.sub, Math.floor(n.w / 6))}</text>}
            </g>
          ))}
        </svg>
        </div>
        <aside className="sg-side">
          {(() => {
            // the recommendation in a few numbers: all workflows, or the one in focus
            const shown = focused ? [focused] : chains;
            const ready = shown.filter((c) => c.status === "runnable").length;
            const standard = shown.filter((c) => c.kind === "reference").length;
            const inputs = new Map<string, string>();
            for (const c of shown) for (const i of c.inputs) {
              const was = inputs.get(i.id);
              if (!was || i.state === "have" || (i.state === "open_data" && was === "missing")) inputs.set(i.id, i.state);
            }
            const count = (st: string) => [...inputs.values()].filter((x) => x === st).length;
            const outputs = new Set(shown.flatMap((c) => c.delivers.map((d) => d.id)));
            return (
              <div className="sg-figures">
                <div className="sg-side-title">{focused ? `Workflow · ${focused.label}` : "At a glance"}</div>
                <div className="sg-fig-grid">
                  <span className="sg-fig"><strong>{shown.length}</strong>workflow{shown.length > 1 ? "s" : ""}</span>
                  <span className="sg-fig ok"><strong>{ready}</strong>ready to run</span>
                  <span className="sg-fig bad"><strong>{shown.length - ready}</strong>to check</span>
                  <span className="sg-fig"><strong>{standard}</strong>standard practice</span>
                </div>
                <div className="sg-side-sub">Data required <span className="muted">· {inputs.size} variables</span></div>
                <div className="sg-bar" role="img" aria-label={`${count("have")} in hand, ${count("open_data")} from open data, ${count("missing")} without a source`}>
                  {inputs.size > 0 && (["have", "open_data", "missing"] as const).map((st) => (
                    <i key={st} className={`sg-bar-${st}`} style={{ width: `${(count(st) / inputs.size) * 100}%` }} />
                  ))}
                </div>
                <div className="sg-bar-key">
                  <span><i className="sw dg-ok" /> {count("have")} in hand</span>
                  <span><i className="sw dg-open" /> {count("open_data")} open data</span>
                  <span><i className="sw dg-bad" /> {count("missing")} no source</span>
                </div>
                <div className="sg-side-sub">Outputs given <span className="muted">· {outputs.size}</span></div>
              </div>
            );
          })()}
          <div className="sg-hover">
            {(() => {
              const n = laid.find((x) => x.key === hover);
              if (!n) return <p className="muted">Point at a box to read it here: what it is, and what it is linked to. Boxes with ▸ open when clicked.</p>;
              return (
                <>
                  <div className="sg-side-title">{n.title}</div>
                  {n.sub && <div className="muted">{n.sub}</div>}
                  <p className="sg-hint">{n.hint}</p>
                </>
              );
            })()}
          </div>
          <div className="sg-legend">
            <span><i className="sw dg-ok" /> ready · delivered · in hand</span>
            <span><i className="sw dg-open" /> from open data</span>
            <span><i className="sw dg-bad" /> to check · no source</span>
          </div>
        </aside>
        </div>
      )}
    </section>
  );
}
