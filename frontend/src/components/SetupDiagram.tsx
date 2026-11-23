import { useState } from "react";
import type { Diagnosis } from "../setupApi";
import { KIND, NATURE, name, sourceOf, STATUS } from "../setupLabels";

// The set-up as a picture: the data it takes (left), the chain of methods from upstream
// to downstream (middle), the results it gives (right). It is drawn from the diagnosis,
// so it changes every time an improvement is accepted.
//
// Hovering a box lights up what it is connected to; clicking a red or dashed box (something
// missing) jumps to the improvements that supply it.

type Tone = "ok" | "open" | "bad" | "plain";
type Node = {
  key: string;
  column: 0 | 1 | 2;
  title: string;
  sub: string;
  tone: Tone;
  dashed?: boolean;
  hint: string;
  target?: string;          // "role:<id>", "data:<id>", "output:<id>": what to improve
  x: number;
  y: number;
};
type Edge = { from: string; to: string; label?: string; optional?: boolean };   // optional = drawn dashed
const MAX_OPTIONAL = 3;

const W = 760;
const NODE_W = 196;
const NODE_H = 40;
const COLUMN_X = [0, (W - NODE_W) / 2, W - NODE_W];
const GAP = [10, 26, 12];        // vertical gap between two boxes of a column
const HEAD = 26;                 // room for the column titles
const MAX_DATA = 7;

const short = (text: string, max = 27) => (text.length > max ? text.slice(0, max - 1) + "…" : text);
const capital = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

function build(d: Diagnosis) {
  const nodes: Omit<Node, "x" | "y">[] = [];
  const edges: Edge[] = [];

  // ---- middle: the methods in the order of the usual workflow, with what is missing ----
  const placed = new Set<string>();
  const method = (id: string) => {
    if (placed.has(id)) return;
    const m = d.setup.methods.find((x) => x.id === id);
    if (!m) return;
    placed.add(id);
    nodes.push({
      key: `m:${id}`, column: 1, title: name(m), sub: m.roles.map(name).join(", ") || "method", tone: "plain",
      hint: `${name(m)} · gives ${m.delivers.map(name).join(", ") || "nothing recorded"}`,
    });
  };
  for (const slot of d.best_template?.slots ?? []) {
    if (slot.filled_by.length) slot.filled_by.forEach((m) => method(m.id));
    else if (slot.mandatory) {
      nodes.push({
        key: `r:${slot.role.id}`, column: 1, title: `+ ${name(slot.role)}`, sub: "missing component", tone: "bad",
        dashed: true, target: `role:${slot.role.id}`, hint: "A usual component is missing: click to see what can fill it",
      });
    }
  }
  d.setup.methods.forEach((m) => method(m.id));
  for (const link of d.links) {
    // an exchange the receiver can run without is drawn dashed
    edges.push({
      from: `m:${link.from}`, to: `m:${link.to}`, optional: link.optional_only,
      label: link.variables.map((v) => name(v) + (link.optional.some((o) => o.id === v.id) && !link.optional_only ? " (optional)" : "")).join(", ")
        + (link.optional_only ? " (optional)" : ""),
    });
  }

  // ---- left: the data. Inputs and calibration data one by one, parameters as one box ----
  const tone = (status: string): Tone =>
    status === "in_hand" ? "ok" : status === "missing" || status === "needs_component" ? "bad" : "open";
  const inputs = d.data.filter((r) => r.kind === "mandatory" || r.kind === "calibration" || (r.kind === "optional" && r.status === "in_hand"));
  const shown = inputs.slice(0, MAX_DATA);
  for (const row of shown) {
    const key = `d:${row.kind}:${row.id}`;
    nodes.push({
      key, column: 0, title: name(row), tone: tone(row.status), dashed: row.kind === "calibration",
      sub: row.kind === "calibration" ? KIND.calibration : NATURE[row.nature],
      hint: `${name(row)} · ${KIND[row.kind]} · ${sourceOf(row)}`,
      target: row.status === "in_hand" ? undefined : `data:${row.id}`,
    });
    row.used_by.forEach((m) => edges.push({ from: key, to: `m:${m.id}`, optional: row.kind === "optional" }));
  }
  // optional inputs the set-up does not use yet: shown dashed, with a dashed link
  const unused = d.data.filter((r) => r.kind === "optional" && r.status !== "in_hand");
  for (const row of unused.slice(0, MAX_OPTIONAL)) {
    const key = `d:optional:${row.id}`;
    nodes.push({
      key, column: 0, title: name(row), tone: "plain", dashed: true,
      sub: `optional · ${NATURE[row.nature]}`,
      hint: `${name(row)} · optional input: the method runs without it, less precisely · ${sourceOf(row)}`,
      target: `data:${row.id}`,
    });
    row.used_by.forEach((m) => edges.push({ from: key, to: `m:${m.id}`, optional: true }));
  }
  const rest = d.data.filter((r) => r.kind === "parameter" || r.kind === "initial")
    .concat(inputs.slice(MAX_DATA)).concat(unused.slice(MAX_OPTIONAL));
  if (rest.length) {
    const have = rest.filter((r) => r.status === "in_hand").length;
    const bad = rest.some((r) => r.status === "missing");
    nodes.push({
      key: "d:rest", column: 0, title: `${rest.length} site descriptions & parameters`, tone: bad ? "bad" : have === rest.length ? "ok" : "open",
      sub: have ? `${have} in hand` : "see the workflow summary",
      hint: rest.map((r) => `${name(r)}: ${STATUS[r.status].text}`).join("\n"),
    });
    new Set(rest.flatMap((r) => r.used_by.map((m) => m.id))).forEach((m) => edges.push({ from: "d:rest", to: `m:${m}` }));
  }

  // ---- right: the expected outputs, or what the last method gives when none was chosen ----
  if (d.outputs.length) {
    for (const o of d.outputs) {
      const ok = o.status === "delivered";
      nodes.push({
        key: `o:${o.id}`, column: 2, title: name(o), tone: ok ? "ok" : "bad", dashed: !ok,
        sub: ok ? "delivered" : o.status === "unreachable" ? "out of reach" : "needs another method",
        hint: o.question ?? name(o), target: ok ? undefined : `output:${o.id}`,
      });
      if (ok) o.produced_by.forEach((m) => edges.push({ from: `m:${m}`, to: `o:${o.id}` }));
    }
  } else {
    const last = d.setup.methods[d.setup.methods.length - 1];
    for (const v of last?.delivers.slice(0, 4) ?? []) {
      nodes.push({ key: `v:${v.id}`, column: 2, title: name(v), sub: "computed variable", tone: "plain", hint: `${name(last)} computes it` });
      edges.push({ from: `m:${last.id}`, to: `v:${v.id}` });
    }
  }

  // ---- positions: each column centred on the tallest one ----
  const heights = [0, 1, 2].map((c) => {
    const n = nodes.filter((x) => x.column === c).length;
    return n ? n * NODE_H + (n - 1) * GAP[c] : 0;
  });
  const height = Math.max(...heights, NODE_H);
  const counter = [0, 0, 0];
  const laid: Node[] = nodes.map((n) => {
    const i = counter[n.column]++;
    return { ...n, x: COLUMN_X[n.column], y: HEAD + (height - heights[n.column]) / 2 + i * (NODE_H + GAP[n.column]) };
  });
  return { nodes: laid, edges, height: height + HEAD + 6 };
}

export default function SetupDiagram({ diagnosis, onPick }: { diagnosis: Diagnosis; onPick: (target: string) => void }) {
  const [hover, setHover] = useState<string | null>(null);
  const { nodes, edges, height } = build(diagnosis);
  const at = new Map(nodes.map((n) => [n.key, n]));
  const live = edges.filter((e) => at.has(e.from) && at.has(e.to));
  const lit = new Set<string>();
  if (hover) {
    lit.add(hover);
    for (const e of live) {
      if (e.from === hover) lit.add(e.to);
      if (e.to === hover) lit.add(e.from);
    }
  }

  function path(e: Edge): { d: string; labelX: number; labelY: number; vertical: boolean } {
    const a = at.get(e.from)!;
    const b = at.get(e.to)!;
    if (a.column === b.column) {
      // method to method: straight down when they follow each other, a side arc otherwise
      const x = a.x + NODE_W / 2;
      if (b.y - a.y <= NODE_H + GAP[1] + 1) {
        return { d: `M${x},${a.y + NODE_H} L${x},${b.y - 4}`, labelX: x + 8, labelY: (a.y + NODE_H + b.y) / 2 + 3, vertical: true };
      }
      const side = a.x + NODE_W;
      const bend = side + 26 + (b.y - a.y) / 12;
      return {
        d: `M${side},${a.y + NODE_H / 2} C${bend},${a.y + NODE_H / 2} ${bend},${b.y + NODE_H / 2} ${side + 4},${b.y + NODE_H / 2}`,
        labelX: bend - 4, labelY: (a.y + b.y) / 2 + NODE_H / 2, vertical: false,
      };
    }
    const x1 = a.x + NODE_W;
    const y1 = a.y + NODE_H / 2;
    const x2 = b.x - 4;
    const y2 = b.y + NODE_H / 2;
    const mid = (x1 + x2) / 2;
    return { d: `M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}`, labelX: mid, labelY: (y1 + y2) / 2, vertical: false };
  }

  return (
    <div className="diagram">
      <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label="Diagram of the set-up: data, methods and results">
        <defs>
          <marker id="dg-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" className="dg-arrow" />
          </marker>
        </defs>
        {["Data", "Methods (upstream to downstream)", "Results"].map((title, c) => (
          <text key={title} x={COLUMN_X[c] + NODE_W / 2} y={12} textAnchor="middle" className="dg-column">{title}</text>
        ))}
        {live.map((e) => {
          const p = path(e);
          const on = !hover || (lit.has(e.from) && lit.has(e.to) && (e.from === hover || e.to === hover));
          return (
            <g key={`${e.from}>${e.to}`} className={`dg-edge${e.optional ? " optional" : ""}${on ? "" : " dim"}${hover && on ? " lit" : ""}`}>
              <path d={p.d} markerEnd="url(#dg-arrow)" />
              {e.label && p.vertical && <text x={p.labelX} y={p.labelY} className="dg-edge-label">{short(e.label, 34)}</text>}
            </g>
          );
        })}
        {nodes.map((n) => (
          <g key={n.key}
             className={`dg-node dg-${n.tone}${n.dashed ? " dashed" : ""}${n.target ? " clickable" : ""}${hover && !lit.has(n.key) ? " dim" : ""}`}
             transform={`translate(${n.x},${n.y})`}
             onMouseEnter={() => setHover(n.key)} onMouseLeave={() => setHover(null)}
             onClick={() => n.target && onPick(n.target)}>
            <title>{n.hint}</title>
            <rect width={NODE_W} height={NODE_H} rx={9} />
            <text x={10} y={17} className="dg-title">{short(capital(n.title))}</text>
            <text x={10} y={31} className="dg-sub">{short(n.sub, 34)}</text>
          </g>
        ))}
      </svg>
      <div className="diagram-legend">
        <span><i className="sw dg-ok" /> in hand / delivered</span>
        <span><i className="sw dg-open" /> available, not chosen yet</span>
        <span><i className="sw dg-bad" /> missing (click to fix)</span>
        <span><i className="sw dg-plain" /> method</span>
        <span><i className="line-solid" /> required link</span>
        <span><i className="line-dashed" /> optional input or exchange</span>
        <span className="muted">Hover a box to see its links.</span>
      </div>
    </div>
  );
}
