import { useEffect, useMemo, useRef, useState } from "react";
import {
  exportUrl,
  getOverview,
  getTerm,
  getTerms,
  searchTerms,
  type Expr,
  type Kind,
  type ListedTerm,
  type Overview,
  type Term,
  type TermRef,
  type ReusedVocabulary,
  type TreeNode,
  type View,
} from "../ontologyApi";
import { EntryHero } from "./EntryFrame";

// The AIO ontology, presented and browsable like a published ontology page (SAREF4WATR,
// Widoco): metadata and downloads, an overview of its modules and how they relate, and a
// cross-reference of every class, property and individual. Each term has its own address
// (#/ontology/<id>), so a term can be linked from anywhere.

const KIND: Record<Kind, { short: string; text: string }> = {
  class: { short: "C", text: "class" },
  object: { short: "OP", text: "object property" },
  datatype: { short: "DP", text: "datatype property" },
  annotation: { short: "AP", text: "annotation property" },
  individual: { short: "I", text: "individual" },
  external: { short: "ext", text: "external term" },
};
const FORMATS: { id: string; label: string }[] = [
  { id: "ttl", label: "Turtle" },
  { id: "rdf", label: "RDF/XML" },
  { id: "jsonld", label: "JSON-LD" },
  { id: "nt", label: "N-Triples" },
];
const LICENCES: Record<string, string> = { "https://creativecommons.org/licenses/by/4.0/": "CC BY 4.0" };
// the views of the ontology: the core first, the extensions used by the recommendation, all
const VIEWS: { id: View; name: string; short: string; prefix: string; note: string }[] = [
  { id: "core", name: "Core", short: "core", prefix: "aio", note: "The knowledge model: problem definition, water system, modelling and data representation, with the value sets that describe them." },
  { id: "requirements", name: "Study requirements", short: "req", prefix: "aioreq", note: "Extension used by the recommendation: the rules a study implies on methods and data." },
  { id: "workflow", name: "Model composition", short: "wf", prefix: "aiowf", note: "Extension used by the recommendation: component roles, interfaces, chain templates, coupling." },
  { id: "software", name: "Software implementations", short: "sw", prefix: "aiosw", note: "Extension used by the recommendation: software modules and curated reference chains." },
  { id: "all", name: "All modules", short: "all", prefix: "", note: "The core and every extension together." },
];
const VIEW = Object.fromEntries(VIEWS.map((v) => [v.id, v])) as Record<View, (typeof VIEWS)[number]>;
// the four axes of the core, each with its colour in the architecture diagram
const AXIS_COLOUR: Record<string, string> = {
  ProblemDefinition: "axis-problem", WaterSystemDefinition: "axis-water", ModelingDefinition: "axis-model", DataRepresentation: "axis-data",
};

// ---- small pieces -------------------------------------------------------------------------

function Badge({ kind }: { kind: Kind }) {
  return <span className={`okind okind-${kind}`} title={KIND[kind].text}>{KIND[kind].short}</span>;
}

function Link({ term, onOpen }: { term: TermRef; onOpen: (id: string) => void }) {
  if (term.external) {
    return (
      <a className="oterm oterm-ext" href={term.iri} target="_blank" rel="noreferrer" title={`${term.id} · ${term.iri}`}>
        {term.label}{term.vocabulary && <span className="ovocab">{term.vocabulary}</span>} ↗
      </a>
    );
  }
  if (term.reused) {
    return (
      <a className={`oterm oterm-${term.kind} oterm-reused`} href={`#/ontology/${term.id}`} title={`${term.id} · reused from ${term.reused}`}
         onClick={(e) => { e.preventDefault(); onOpen(term.id); }}>
        {term.label}<span className="ovocab ovocab-reused">{term.reused}</span>
      </a>
    );
  }
  const ext = term.module && term.module !== "core" ? VIEW[term.module] : null;
  return (
    <a className={`oterm oterm-${term.kind}`} href={`#/ontology/${term.id}`} title={`${ext ? ext.prefix : "aio"}:${term.id}${ext ? ` · extension ${ext.name}` : ""}`}
       onClick={(e) => { e.preventDefault(); onOpen(term.id); }}>
      {term.label}{ext && <span className="omodtag">{ext.short}</span>}
    </a>
  );
}

function ExprView({ e, onOpen }: { e: Expr; onOpen: (id: string) => void }) {
  if ("iri" in e) return <Link term={e} onOpen={onOpen} />;
  if ("literal" in e) return <code>{e.literal}</code>;
  if ("value" in e) return <span className="olit">“{e.value}”{e.lang && <sup>@{e.lang}</sup>}{e.datatype && <sup> {e.datatype}</sup>}</span>;
  if ("list" in e) return <span className="oexpr">{e.list.map((x, i) => <span key={i}>{i > 0 && <span className="oop"> ∘ </span>}<ExprView e={x} onOpen={onOpen} /></span>)}</span>;
  if ("op" in e) return <span className="oexpr">({e.items.map((x, i) => <span key={i}>{i > 0 && <span className="oop"> {e.op} </span>}<ExprView e={x} onOpen={onOpen} /></span>)})</span>;
  if ("restriction" in e) {
    const r = e.restriction;
    return (
      <span className="oexpr"><ExprView e={r.on} onOpen={onOpen} /> <span className="oop">{r.kind ?? "?"}</span>{" "}
        {r.value && <ExprView e={r.value} onOpen={onOpen} />}{r.class && <> <ExprView e={r.class} onOpen={onOpen} /></>}</span>
    );
  }
  return <span className="muted">{e.text}</span>;
}

function Row({ title, help, children }: { title: string; help?: string; children: React.ReactNode }) {
  return (
    <div className="orow">
      <dt title={help}>{title}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Links({ items, onOpen, empty = "none" }: { items: Expr[] | undefined; onOpen: (id: string) => void; empty?: string }) {
  if (!items || items.length === 0) return <span className="muted">{empty}</span>;
  return <span className="olinks">{items.map((x, i) => <ExprView key={i} e={x} onOpen={onOpen} />)}</span>;
}

function Copy({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button className="ocopy" title="Copy" onClick={() => navigator.clipboard?.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1400); })}>
      {done ? "✓" : "⧉"}
    </button>
  );
}

// ---- the overview diagram: classes and the object properties between them -----------------------

const BOX_W = 176, BOX_H = 44;

// A deterministic force layout: linked boxes pull together, every pair pushes apart, then
// overlapping boxes are separated and the whole drawing is fitted to the frame.
function layout(ids: string[], edges: { from: string; to: string }[], W: number, H: number) {
  const n = ids.length;
  const p = ids.map((_, i) => {
    const a = (i / Math.max(n, 1)) * Math.PI * 2;
    return { x: Math.cos(a) * 420, y: Math.sin(a) * 260, dx: 0, dy: 0 };
  });
  const index = new Map(ids.map((id, i) => [id, i]));
  const links = edges.map((e) => [index.get(e.from), index.get(e.to)]).filter(([a, b]) => a !== undefined && b !== undefined) as [number, number][];
  const k = 270;
  for (let step = 0; step < 450; step++) {
    const t = 36 * (1 - step / 450) + 1;
    for (const a of p) { a.dx = 0; a.dy = 0; }
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const dx = p[i].x - p[j].x, dy = (p[i].y - p[j].y) * 1.5;
        const d = Math.max(Math.hypot(dx, dy), 1);
        const f = (k * k) / d;
        p[i].dx += (dx / d) * f; p[i].dy += (dy / d) * f;
        p[j].dx -= (dx / d) * f; p[j].dy -= (dy / d) * f;
      }
    }
    for (const [a, b] of links) {
      const dx = p[a].x - p[b].x, dy = p[a].y - p[b].y;
      const d = Math.max(Math.hypot(dx, dy), 1);
      const f = (d * d) / k / 2;
      p[a].dx -= (dx / d) * f; p[a].dy -= (dy / d) * f;
      p[b].dx += (dx / d) * f; p[b].dy += (dy / d) * f;
    }
    for (const a of p) {
      a.dx -= a.x * 0.015; a.dy -= a.y * 0.025;               // a little gravity towards the centre
      const d = Math.max(Math.hypot(a.dx, a.dy), 1);
      a.x += (a.dx / d) * Math.min(d, t); a.y += (a.dy / d) * Math.min(d, t);
    }
  }
  const xs = p.map((a) => a.x), ys = p.map((a) => a.y);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const sx = (W - BOX_W - 40) / Math.max(x1 - x0, 1), sy = (H - BOX_H - 40) / Math.max(y1 - y0, 1);
  for (const a of p) { a.x = 20 + BOX_W / 2 + (a.x - x0) * sx; a.y = 20 + BOX_H / 2 + (a.y - y0) * sy; }
  for (let round = 0; round < 200; round++) {
    let moved = false;
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const ox = BOX_W + 70 - Math.abs(p[i].x - p[j].x), oy = BOX_H + 56 - Math.abs(p[i].y - p[j].y);
        if (ox > 0 && oy > 0) {
          moved = true;
          if (ox / BOX_W < oy / BOX_H) { const s = (p[i].x < p[j].x ? -1 : 1) * ox / 2; p[i].x += s; p[j].x -= s; }
          else { const s = (p[i].y < p[j].y ? -1 : 1) * oy / 2; p[i].y += s; p[j].y -= s; }
        }
      }
    }
    for (const a of p) {
      a.x = Math.min(W - BOX_W / 2 - 8, Math.max(BOX_W / 2 + 8, a.x));
      a.y = Math.min(H - BOX_H / 2 - 8, Math.max(BOX_H / 2 + 8, a.y));
    }
    if (!moved) break;
  }
  return new Map(ids.map((id, i) => [id, { x: p[i].x, y: p[i].y }]));
}

// Zoom (Ctrl/⌘ + wheel, pinch, buttons) and move (drag) for an SVG drawing of size W x H.
// The plain wheel is left to the page, so the graph never traps the scrolling.
function useZoom(W: number, H: number) {
  const full = useMemo(() => ({ x: 0, y: 0, w: W, h: H }), [W, H]);
  const [view, setView] = useState(full);
  const svg = useRef<SVGSVGElement>(null);
  const drag = useRef<{ x: number; y: number; view: typeof full; moved: boolean } | null>(null);
  const moved = useRef(false);
  const clamp = (v: typeof full) => {
    const w = Math.min(W, Math.max(W / 8, v.w));
    const h = (w / W) * H;
    return { w, h, x: Math.min(W - w, Math.max(0, v.x)), y: Math.min(H - h, Math.max(0, v.y)) };
  };
  const zoomAt = (factor: number, cx?: number, cy?: number) => setView((v) => {
    const px = cx ?? v.x + v.w / 2, py = cy ?? v.y + v.h / 2;
    const w = v.w / factor, h = v.h / factor;
    return clamp({ x: px - ((px - v.x) * w) / v.w, y: py - ((py - v.y) * h) / v.h, w, h });
  });
  useEffect(() => {
    const el = svg.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return;      // a trackpad pinch also arrives with ctrlKey
      e.preventDefault();
      const m = el.getScreenCTM();
      if (!m) return;
      const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(m.inverse());
      zoomAt(e.deltaY < 0 ? 1.2 : 1 / 1.2, pt.x, pt.y);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  });
  const handlers = {
    onPointerDown: (e: React.PointerEvent) => {
      if (e.button !== 0) return;
      drag.current = { x: e.clientX, y: e.clientY, view, moved: false };
      moved.current = false;
      // keep the pan going if the pointer slips out of the drawing
      try { svg.current?.setPointerCapture(e.pointerId); } catch { /* not a captured pointer */ }
    },
    onPointerMove: (e: React.PointerEvent) => {
      const d = drag.current;
      if (!d || !svg.current) return;
      const dx = e.clientX - d.x, dy = e.clientY - d.y;
      if (!d.moved && Math.hypot(dx, dy) < 4) return;
      d.moved = true; moved.current = true;
      // screen pixels per drawing unit, as drawn (the drawing may be centred with margins)
      const m = svg.current.getScreenCTM();
      const scale = m && m.a ? 1 / m.a : d.view.w / svg.current.getBoundingClientRect().width;
      setView(clamp({ ...d.view, x: d.view.x - dx * scale, y: d.view.y - dy * scale }));
    },
    onPointerUp: (e?: React.PointerEvent) => {
      drag.current = null;
      if (e && svg.current?.hasPointerCapture(e.pointerId)) svg.current.releasePointerCapture(e.pointerId);
    },
    onPointerLeave: () => { drag.current = null; },
  };
  // the pointer, in the drawing's coordinates
  const toSvg = (e: { clientX: number; clientY: number }) => {
    const m = svg.current?.getScreenCTM();
    return m ? new DOMPoint(e.clientX, e.clientY).matrixTransform(m.inverse()) : null;
  };
  return { svg, view, zoom: W / view.w, zoomAt, reset: () => setView(full), handlers, wasDrag: () => moved.current, toSvg };
}

const countInstances = (n: TreeNode): number => n.instances + n.children.reduce((sum, c) => sum + countInstances(c), 0);
const MODULE_COLOUR: Record<string, string> = { requirements: "mod-req", workflow: "mod-wf", software: "mod-sw" };

type Box = TreeNode & { axis?: string; context?: boolean };
type Edge = { from: string; to: string; props: TermRef[] };

function ModuleDiagram({ overview, onOpen, selected }: { overview: Overview; onOpen: (id: string) => void; selected: string | null }) {
  const [hover, setHover] = useState<string | null>(null);
  // Core: the classes directly under the four axes (the semantic architecture), coloured by
  // axis. Extension: its classes (coloured by module) and the classes it builds on (dashed).
  const { nodes, edges } = useMemo(() => {
    const rootOf = new Map<string, TreeNode>();
    const axisOf = new Map<string, string>();
    const walk = (node: TreeNode, box: TreeNode, axis: string | null) => {
      rootOf.set(node.id, box);
      if (axis) axisOf.set(box.id, axis);
      node.children.forEach((c) => walk(c, box, axis));
    };
    for (const root of overview.hierarchy) {
      if (overview.module === "core" && root.group === "axis" && root.children.length) {
        rootOf.set(root.id, root);
        axisOf.set(root.id, root.id);
        root.children.forEach((c) => walk(c, c, root.id));
      } else if (root.group !== "descriptor") {
        walk(root, root, root.group === "axis" ? root.id : null);
      }
    }
    for (const c of overview.linked) {
      if (!rootOf.has(c.id)) rootOf.set(c.id, { ...c, instances: 0, children: [], group: "descriptor", context: true } as TreeNode);
    }
    const grouped = new Map<string, Edge>();
    for (const rel of overview.relations) {
      const a = rootOf.get(rel.from)?.id;
      const b = rootOf.get(rel.to)?.id;
      if (!a || !b || a === b) continue;
      const key = `${a}>${b}`;
      if (!grouped.has(key)) grouped.set(key, { from: a, to: b, props: [] });
      if (!grouped.get(key)!.props.some((p) => p.id === rel.property.id)) grouped.get(key)!.props.push(rel.property);
    }
    const linked = new Set([...grouped.values()].flatMap((e) => [e.from, e.to]));
    const boxes = new Map<string, Box>();
    for (const box of rootOf.values()) {
      if (linked.has(box.id) && !boxes.has(box.id)) boxes.set(box.id, { ...box, axis: axisOf.get(box.id) });
    }
    const shown = [...boxes.values()].sort((x, y) => (x.axis ?? "~").localeCompare(y.axis ?? "~") || (y.total ?? y.instances) - (x.total ?? x.instances));
    return { nodes: shown, edges: [...grouped.values()] };
  }, [overview]);

  const W = 1500, H = 860;
  const laid = useMemo(() => layout(nodes.map((n) => n.id), edges, W, H), [nodes, edges]);
  const { svg, view, zoom, zoomAt, reset, handlers, toSvg } = useZoom(W, H);
  // Boxes the user moved: their position replaces the computed one (until "Reset layout").
  const [placed, setPlaced] = useState<Record<string, { x: number; y: number }>>({});
  useEffect(() => setPlaced({}), [laid]);                  // another module: its own layout
  const at = useMemo(() => {
    const m = new Map(laid);
    for (const [id, p] of Object.entries(placed)) if (m.has(id)) m.set(id, p);
    return m;
  }, [laid, placed]);
  // a box being dragged: grabbed at (dx, dy) from its centre; a press without a move opens it
  const grab = useRef<{ id: string; dx: number; dy: number; x0: number; y0: number; moved: boolean } | null>(null);
  function grabBox(e: React.PointerEvent, id: string) {
    if (e.button !== 0) return;
    e.stopPropagation();                                  // not a move of the whole drawing
    const pt = toSvg(e);
    const p = at.get(id);
    if (!pt || !p) return;
    grab.current = { id, dx: pt.x - p.x, dy: pt.y - p.y, x0: e.clientX, y0: e.clientY, moved: false };
    svg.current?.setPointerCapture(e.pointerId);
  }
  const dragHandlers = {
    onPointerDown: handlers.onPointerDown,
    onPointerMove: (e: React.PointerEvent) => {
      const g = grab.current;
      if (!g) { handlers.onPointerMove(e); return; }
      if (!g.moved && Math.hypot(e.clientX - g.x0, e.clientY - g.y0) < 4) return;
      g.moved = true;
      const pt = toSvg(e);
      if (!pt) return;
      const x = Math.min(W - BOX_W / 2 - 4, Math.max(BOX_W / 2 + 4, pt.x - g.dx));
      const y = Math.min(H - BOX_H / 2 - 4, Math.max(BOX_H / 2 + 4, pt.y - g.dy));
      setPlaced((old) => ({ ...old, [g.id]: { x, y } }));
    },
    onPointerUp: (e: React.PointerEvent) => {
      const g = grab.current;
      grab.current = null;
      if (svg.current?.hasPointerCapture(e.pointerId)) svg.current.releasePointerCapture(e.pointerId);
      if (g && !g.moved) onOpen(g.id);                    // a click: open the class
      handlers.onPointerUp(e);
    },
    onPointerLeave: () => { if (!grab.current) handlers.onPointerLeave(); },
  };
  const shownEdges = edges.filter((e) => at.has(e.from) && at.has(e.to));
  const active = hover ? shownEdges.filter((e) => e.from === hover || e.to === hover) : [];
  const isOn = (e: Edge) => !hover || e.from === hover || e.to === hover;
  const colourOf = (n: Box) => n.axis ? AXIS_COLOUR[n.axis] : n.context ? "" : MODULE_COLOUR[n.module ?? ""] ?? "";
  const edgeColour = (e: Edge) => {
    const from = nodes.find((n) => n.id === e.from);
    return from ? colourOf(from) : "";
  };

  return (
    <div className="odiagram">
      <div className="odiagram-frame">
        <svg ref={svg} viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`} role="img" {...dragHandlers}
             aria-label="Classes of the AIO ontology and the object properties between them">
          <defs>
            {["edge", "edge-on"].map((id) => (
              <marker key={id} id={`o${id}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0,0 L10,5 L0,10 z" className={`oarrowhead ${id}`} />
              </marker>
            ))}
          </defs>
          {shownEdges.map((e) => {
            const a = at.get(e.from)!, b = at.get(e.to)!;
            // a gentle curve, ending at the border of the target box
            // each direction bends to its own side, so a property and its inverse do not overlap
            const len = Math.max(Math.hypot(b.x - a.x, b.y - a.y), 1);
            const bend = Math.min(70, 22 + len * 0.12);
            const mx = (a.x + b.x) / 2 - ((b.y - a.y) / len) * bend, my = (a.y + b.y) / 2 + ((b.x - a.x) / len) * bend;
            const ang = Math.atan2(b.y - my, b.x - mx);
            const reach = Math.min(Math.abs((BOX_W / 2 + 4) / Math.cos(ang || 1e-6)), Math.abs((BOX_H / 2 + 4) / Math.sin(ang || 1e-6)));
            const ex = b.x - Math.cos(ang) * reach, ey = b.y - Math.sin(ang) * reach;
            const lx = (a.x + 2 * mx + ex) / 4, ly = (a.y + 2 * my + ey) / 4;
            const on = isOn(e);
            const label = e.props.length > 1 ? `${e.props[0].label} +${e.props.length - 1}` : e.props[0].label;
            return (
              <g key={`${e.from}>${e.to}`} className={`oedge-g ${edgeColour(e)}${on ? (hover ? " on" : "") : " off"}`}>
                <path d={`M${a.x},${a.y} Q${mx},${my} ${ex},${ey}`} className="oedge" markerEnd={`url(#o${hover && on ? "edge-on" : "edge"})`}>
                  <title>{e.props.map((p) => p.label).join(", ")}</title>
                </path>
                <text x={lx} y={ly} textAnchor="middle" className="oedge-label">
                  <title>{e.props.map((p) => p.label).join(", ")}</title>
                  {label}
                </text>
              </g>
            );
          })}
          {nodes.map((n) => {
            const p = at.get(n.id)!;
            const dim = hover && hover !== n.id && !active.some((e) => e.from === n.id || e.to === n.id);
            return (
              <g key={n.id} transform={`translate(${p.x},${p.y})`}
                 className={`onode ${colourOf(n)}${dim ? " off" : ""}${hover === n.id ? " on" : ""}${selected === n.id ? " picked" : ""}${n.context ? " onode-context" : ""}${n.reused ? " onode-reused" : ""}`}
                 onMouseEnter={() => { if (!grab.current) setHover(n.id); }} onMouseLeave={() => { if (!grab.current) setHover(null); }}
                 onPointerDown={(e) => grabBox(e, n.id)}>
                <rect x={-BOX_W / 2} y={-BOX_H / 2} width={BOX_W} height={BOX_H} rx={11} />
                <text y={-3} textAnchor="middle" className="onode-title">{n.label.length > 24 ? n.label.slice(0, 23) + "…" : n.label}</text>
                <text y={13} textAnchor="middle" className="onode-sub">
                  {n.context ? (n.reused ? `reused · ${n.reused}` : `${n.module && n.module !== "core" ? VIEW[n.module].name.toLowerCase() : "core"} class`) : `${n.children.length} subclass${n.children.length === 1 ? "" : "es"} · ${n.total ?? countInstances(n)} ind.`}
                </text>
              </g>
            );
          })}
        </svg>
        <div className="fmap-zoom odiagram-zoom" role="group" aria-label="Zoom">
          <button title="Zoom in" onClick={() => zoomAt(1.5)} disabled={zoom >= 7.9}>+</button>
          <button title="Zoom out" onClick={() => zoomAt(1 / 1.5)} disabled={zoom <= 1.01}>−</button>
          <button title="Whole graph" onClick={reset} disabled={zoom <= 1.01}>⤢</button>
          {zoom > 1.01 && <span className="fmap-zoom-level">×{zoom.toFixed(1)}</span>}
        </div>
        {Object.keys(placed).length > 0 && (
          <button className="odiagram-relayout" onClick={() => setPlaced({})} title="Put every box back where the layout placed it">Reset layout</button>
        )}
        <div className="fmap-help">Drag a box to move it · click it to open it · Ctrl + scroll to zoom · drag the background to pan</div>
        {hover && (
          <div className="odiagram-pop">
            <strong>{nodes.find((n) => n.id === hover)?.label}</strong>
            {active.length === 0 && <span className="muted">No relation shown.</span>}
            {active.map((e) => (
              <div key={`${e.from}>${e.to}`} className="orel">
                <span className="muted">{e.from === hover ? "to" : "from"} {nodes.find((n) => n.id === (e.from === hover ? e.to : e.from))?.label}</span>
                <span className="orel-props">{e.props.map((p) => p.label).join(" · ")}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="odiagram-legend">
        {overview.module === "core" && Object.entries(AXIS_COLOUR).map(([id, css]) => (
          <button key={id} className={`oaxis ${css}`} onClick={() => onOpen(id)}>
            {overview.hierarchy.find((h) => h.id === id)?.label ?? id}
          </button>
        ))}
        {overview.module !== "core" && overview.module !== "all" && (
          <>
            <span className={`oaxis ${MODULE_COLOUR[overview.module] ?? ""}`}>{VIEW[overview.module].name}</span>
            {overview.linked.length > 0 && <span className="oaxis onode-context-key">classes it builds on</span>}
          </>
        )}
        <span className="muted small">
          {overview.module === "core"
            ? "Boxes: the classes directly under each axis, with their subclasses. Arrows: object properties, from domain to range."
            : "Arrows: object properties, from domain to range. Hover a box to see all its relations."}
        </span>
      </div>
    </div>
  );
}

// ---- how AIO links to other ontologies: imports, reused vocabularies, alignments -----------------

function LinkMap({ overview }: { overview: Overview }) {
  const extensions = overview.modules.filter((m) => m.key && m.key !== "core" && m.key !== "alignments");
  const reused = overview.reused;
  const aligned = overview.alignments;
  const W = 1100, rowH = 34, H = Math.max(260, Math.max(reused.length, aligned.length, extensions.length + 1) * rowH + 90);
  const core = { x: W / 2, y: H / 2 };
  const column = (n: number, i: number) => 60 + (i + 0.5) * ((H - 80) / Math.max(n, 1));
  return (
    <div className="olinkmap">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="How AIO links to other ontologies">
        <text x={150} y={24} textAnchor="middle" className="olm-head">Reuses terms of</text>
        <text x={W / 2} y={24} textAnchor="middle" className="olm-head">AIO</text>
        <text x={W - 150} y={24} textAnchor="middle" className="olm-head">Aligned to</text>
        {reused.map((g, i) => {
          const y = column(reused.length, i);
          return (
            <g key={g.vocabulary}>
              <path d={`M${230},${y} C${380},${y} ${380},${core.y} ${core.x - 110},${core.y}`} className="olm-edge olm-reuse" />
              <text x={238} y={y - 5} textAnchor="start" className="olm-label">{g.terms.length} term{g.terms.length > 1 ? "s" : ""}</text>
              <g transform={`translate(150,${y})`} className="olm-node olm-reused">
                <title>{g.name}</title>
                <rect x={-80} y={-14} width={160} height={28} rx={8} />
                <text y={5} textAnchor="middle">{g.vocabulary}</text>
              </g>
            </g>
          );
        })}
        {aligned.map((g, i) => {
          const y = column(aligned.length, i);
          return (
            <g key={g.vocabulary}>
              <path d={`M${core.x + 110},${core.y} C${W - 380},${core.y} ${W - 380},${y} ${W - 230},${y}`} className="olm-edge olm-align" />
              <text x={W - 238} y={y - 5} textAnchor="end" className="olm-label">{g.count} mapping{g.count > 1 ? "s" : ""}</text>
              <g transform={`translate(${W - 150},${y})`} className="olm-node olm-aligned">
                <title>{g.name}</title>
                <rect x={-80} y={-14} width={160} height={28} rx={8} />
                <text y={5} textAnchor="middle">{g.vocabulary}</text>
              </g>
            </g>
          );
        })}
        {extensions.map((m, i) => {
          const x = core.x - ((extensions.length - 1) * 186) / 2 + i * 186;
          const y = core.y + 95;
          return (
            <g key={m.iri}>
              <path d={`M${x},${y - 16} L${core.x},${core.y + 24}`} className="olm-edge olm-import" markerEnd="url(#olm-arrow)" />
              <g transform={`translate(${x},${y})`} className="olm-node olm-ext">
                <title>{m.title}</title>
                <rect x={-88} y={-16} width={176} height={32} rx={8} />
                <text y={5} textAnchor="middle">{m.name}</text>
              </g>
            </g>
          );
        })}
        <defs>
          <marker id="olm-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#c98a2e" /></marker>
        </defs>
        <g transform={`translate(${core.x},${core.y})`} className="olm-node olm-core">
          <rect x={-110} y={-24} width={220} height={48} rx={12} />
          <text y={-2} textAnchor="middle">AIO core</text>
          <text y={14} textAnchor="middle" className="olm-sub">{overview.namespace}</text>
        </g>
        {extensions.length > 0 && <text x={core.x} y={core.y + 135} textAnchor="middle" className="olm-label">extensions import the core</text>}
      </svg>
      <div className="olm-legend">
        <span><i className="olm-key olm-reuse" /> reuses: AIO uses their terms with the original IRI (no import of the whole vocabulary)</span>
        <span><i className="olm-key olm-align" /> aligned: AIO terms are mapped to theirs (SKOS mappings, sub-class links)</span>
        <span><i className="olm-key olm-import" /> imports: an extension builds on the core</span>
      </div>
    </div>
  );
}

function ReusedTable({ groups, onOpen }: { groups: ReusedVocabulary[]; onOpen: (id: string) => void }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="oaligntable">
      {groups.map((g) => {
        const classes = g.terms.filter((t) => t.kind === "class");
        return (
          <div key={g.vocabulary} className={`oalign-group${open === g.vocabulary ? " on" : ""}`}>
            <button className="oalign-head" aria-expanded={open === g.vocabulary} onClick={() => setOpen(open === g.vocabulary ? null : g.vocabulary)}>
              <span className="ovocab ovocab-reused ovocab-big">{g.vocabulary}</span>
              <span className="oalign-name">{g.name}</span>
              <span className="oalign-rel">{classes.length ? `classes: ${classes.map((c) => c.label).join(", ")}` : `${g.terms.length} properties`}</span>
              <span className="oalign-n">{g.terms.length}</span>
              <span className="muted">{open === g.vocabulary ? "▾" : "▸"}</span>
            </button>
            {open === g.vocabulary && (
              <table className="otable">
                <tbody>
                  {g.terms.map((t) => (
                    <tr key={t.id}>
                      <td><Link term={t} onOpen={onOpen} /></td>
                      <td><code>{t.id}</code></td>
                      <td className="muted">{KIND[t.kind].text}</td>
                      <td className="muted">{t.instances ? `${t.instances} AIO individuals` : t.uses ? `used ${t.uses}×` : "declared"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {open === g.vocabulary && <p className="muted small oreused-src">Specification: <a href={g.url} target="_blank" rel="noreferrer">{g.url}</a></p>}
          </div>
        );
      })}
    </div>
  );
}

// ---- alignments: one row per vocabulary, its mappings on demand ---------------------------------

function AlignmentTable({ groups, onOpen }: { groups: Overview["alignments"]; onOpen: (id: string) => void }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="oaligntable">
      {groups.map((g) => (
        <div key={g.vocabulary} className={`oalign-group${open === g.vocabulary ? " on" : ""}`}>
          <button className="oalign-head" aria-expanded={open === g.vocabulary} onClick={() => setOpen(open === g.vocabulary ? null : g.vocabulary)}>
            <span className="ovocab ovocab-big">{g.vocabulary}</span>
            <span className="oalign-name">{g.name}</span>
            <span className="oalign-rel">{Object.entries(g.relations).map(([r, n]) => `${n} ${r}`).join(" · ")}</span>
            <span className="oalign-n">{g.count}</span>
            <span className="muted">{open === g.vocabulary ? "▾" : "▸"}</span>
          </button>
          {open === g.vocabulary && (
            <table className="otable">
              <tbody>
                {g.pairs.map((pair, i) => (
                  <tr key={i}>
                    <td><Link term={pair.term} onOpen={onOpen} /></td>
                    <td className="orelation">{pair.relation}</td>
                    <td><Link term={pair.target} onOpen={onOpen} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ))}
    </div>
  );
}

// ---- the browser's side list ------------------------------------------------------------------

// the classes (or properties) above a term in a tree, outermost first; null if it is not there
function pathTo(nodes: TreeNode[], id: string): string[] | null {
  for (const n of nodes) {
    if (n.id === id) return [];
    const below = pathTo(n.children, id);
    if (below) return [n.id, ...below];
  }
  return null;
}

// expand: the branches to open so that the selected term is visible
function Tree({ nodes, current, onOpen, expand, depth = 0 }: {
  nodes: TreeNode[]; current: string | null; onOpen: (id: string) => void; expand: string[]; depth?: number;
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  // a term selected elsewhere (graph, links, search) opens its branch, even one closed by hand
  const expandKey = expand.join("|");
  useEffect(() => {
    if (expand.length) setOpen((old) => ({ ...old, ...Object.fromEntries(expand.map((id) => [id, true])) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expandKey]);
  return (
    <ul className="otree" role={depth ? "group" : "tree"}>
      {nodes.map((n) => {
        const expanded = open[n.id] ?? expand.includes(n.id);
        return (
          <li key={n.id} role="treeitem" aria-expanded={n.children.length ? expanded : undefined}>
            <div className={`otree-row${current === n.id ? " on" : ""}`} style={{ paddingLeft: 6 + depth * 14 }}>
              {n.children.length > 0
                ? <button className="otree-caret" aria-label={expanded ? "Collapse" : "Expand"} onClick={() => setOpen({ ...open, [n.id]: !expanded })}>{expanded ? "▾" : "▸"}</button>
                : <span className="otree-caret" />}
              <a href={`#/ontology/${n.id}`} onClick={(e) => { e.preventDefault(); onOpen(n.id); }}>{n.label}</a>
              {(n.total ?? n.instances) > 0 && <span className="otree-n">{n.total ?? n.instances}</span>}
            </div>
            {expanded && n.children.length > 0 && <Tree nodes={n.children} current={current} onOpen={onOpen} expand={expand} depth={depth + 1} />}
          </li>
        );
      })}
    </ul>
  );
}

function propertyTree(terms: ListedTerm[], kind: Kind): TreeNode[] {
  const own = terms.filter((t) => t.kind === kind);
  const ids = new Set(own.map((t) => t.id));
  const node = (t: ListedTerm): TreeNode => ({
    id: t.id, label: t.label, kind: t.kind, iri: "", external: false, instances: 0,
    children: own.filter((c) => c.parent === t.id).map(node),
  });
  return own.filter((t) => !t.parent || !ids.has(t.parent)).map(node);
}

// ---- one term ---------------------------------------------------------------------------------

function TermView({ term, onOpen }: { term: Term; onOpen: (id: string) => void }) {
  const [all, setAll] = useState(false);
  const [filter, setFilter] = useState("");
  const instances = (term.instances ?? []).filter((i) => !filter || i.label.toLowerCase().includes(filter.toLowerCase()));
  const [prefix, local] = term.curie.includes(":") && !term.curie.startsWith("http") ? term.curie.split(":") : ["x", term.iri];
  const ns = term.iri.slice(0, term.iri.length - local.length);
  const head = `PREFIX ${prefix}: <${ns}>\nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n`;
  const sparql = term.kind === "class"
    ? `${head}SELECT ?x ?label WHERE {\n  ?x a ${term.curie} ;\n     rdfs:label ?label .\n}`
    : term.kind === "individual"
      ? `${head}SELECT ?p ?o WHERE {\n  ${term.curie} ?p ?o .\n}`
      : `${head}SELECT ?s ?o WHERE {\n  ?s ${term.curie} ?o .\n}`;
  const module = term.module ? VIEW[term.module] : null;
  const other = term.labels.filter((l) => l.lang && l.lang !== "en");

  return (
    <article className="oterm-card">
      {(term.ancestors ?? []).slice(0, 2).map((path, i) => (
        <div key={i} className="ocrumbs">
          {path.map((p) => <span key={p.id}><Link term={p} onOpen={onOpen} /> ›</span>)} <span>{term.label}</span>
        </div>
      ))}
      <div className="oterm-head">
        <Badge kind={term.kind} />
        <h3>{term.label}</h3>
        <code className="ocurie">{term.curie}</code>
        {module && <span className={`omodbadge omod-${term.module}`} title={module.note}>{module.id === "core" ? "Core" : `Extension · ${module.name}`}</span>}
        {term.reused_from && <span className="omodbadge omod-reused">Reused · {term.reused_from.vocabulary}</span>}
      </div>
      <div className="oiri"><span className="muted">IRI</span> <code>{term.iri}</code> <Copy text={term.iri} /></div>
      {term.reused_from && (
        <div className="oreused-banner">
          <span className="ovocab ovocab-reused ovocab-big">{term.reused_from.vocabulary}</span>
          <span>
            <strong>Reused from {term.reused_from.name}.</strong> AIO does not define this term: it uses it with its
            original IRI, so AIO data stay readable by any tool that knows {term.reused_from.vocabulary}. Below, how AIO uses it.{" "}
            <a href={term.iri} target="_blank" rel="noreferrer">Original definition ↗</a> ·{" "}
            <a href={term.reused_from.url} target="_blank" rel="noreferrer">{term.reused_from.vocabulary} specification ↗</a>
          </span>
        </div>
      )}
      {term.definition ? <p className="odef">{term.definition}</p> : !term.reused_from && <p className="odef muted">No definition recorded.</p>}
      {term.comment && term.comment !== term.definition && <p className="ocomment">{term.comment}</p>}

      <dl className="orows">
        {other.length > 0 && <Row title="Other labels">{other.map((l) => <span key={l.value} className="olit">“{l.value}”<sup>@{l.lang}</sup> </span>)}</Row>}

        {term.kind === "class" && (
          <>
            <Row title="Superclasses" help="rdfs:subClassOf"><Links items={term.superclasses} onOpen={onOpen} empty={term.reused_from ? "not stated by AIO (see the original definition)" : "top-level class"} /></Row>
            <Row title="Subclasses"><Links items={term.subclasses} onOpen={onOpen} /></Row>
            {(term.restrictions ?? []).length > 0 && <Row title="Restrictions" help="anonymous superclasses"><Links items={term.restrictions} onOpen={onOpen} /></Row>}
            {(term.equivalent ?? []).length > 0 && <Row title="Equivalent to"><Links items={term.equivalent} onOpen={onOpen} /></Row>}
            {(term.disjoint ?? []).length > 0 && <Row title="Disjoint with"><Links items={term.disjoint} onOpen={onOpen} /></Row>}
            <Row title="In domain of" help="properties whose subject is of this class"><Links items={term.in_domain_of} onOpen={onOpen} /></Row>
            <Row title="In range of" help="properties whose value is of this class"><Links items={term.in_range_of} onOpen={onOpen} /></Row>
          </>
        )}

        {(term.kind === "object" || term.kind === "datatype" || term.kind === "annotation") && (
          <>
            <Row title="Domain" help="rdfs:domain"><Links items={term.domain} onOpen={onOpen} empty="not restricted" /></Row>
            <Row title="Range" help="rdfs:range"><Links items={term.range} onOpen={onOpen} empty="not restricted" /></Row>
            <Row title="Superproperties"><Links items={term.superproperties} onOpen={onOpen} /></Row>
            <Row title="Subproperties"><Links items={term.subproperties} onOpen={onOpen} /></Row>
            {(term.inverse ?? []).length > 0 && <Row title="Inverse of"><Links items={term.inverse} onOpen={onOpen} /></Row>}
            {(term.chains ?? []).length > 0 && <Row title="Property chain" help="owl:propertyChainAxiom: following these properties in turn implies this one"><Links items={term.chains} onOpen={onOpen} /></Row>}
            {(term.disjoint ?? []).length > 0 && <Row title="Disjoint with"><Links items={term.disjoint} onOpen={onOpen} /></Row>}
            {(term.characteristics ?? []).length > 0 && <Row title="Characteristics">{term.characteristics!.map((c) => <span key={c} className="pill">{c}</span>)}</Row>}
          </>
        )}

        {term.kind === "individual" && (
          <>
            <Row title="Instance of"><Links items={term.classes} onOpen={onOpen} /></Row>
            {(term.facts ?? []).map((f) => (
              <Row key={f.property.id} title={f.property.label}><Links items={f.values} onOpen={onOpen} /></Row>
            ))}
          </>
        )}

        {term.alignments.length > 0 && (
          <Row title="Alignments" help="Mappings to external vocabularies (module aio-alignments)">
            <span className="oaligns">
              {term.alignments.map((a, i) => (
                <span key={i} className="oalign"><span className="orelation">{a.relation}</span> <Link term={a.target} onOpen={onOpen} /></span>
              ))}
            </span>
          </Row>
        )}
        {term.annotations.map((a) => (
          <Row key={a.property.iri} title={a.property.label}><Links items={a.values} onOpen={onOpen} /></Row>
        ))}
      </dl>

      {term.kind === "class" && (term.instances_total ?? 0) > 0 && (
        <section className="osub">
          <div className="osub-head">
            <h4>Individuals <span className="muted">· {term.instances?.length} direct{term.instances_total !== term.instances?.length ? `, ${term.instances_total} with subclasses` : ""}</span></h4>
            {(term.instances?.length ?? 0) > 12 && <input className="ofilter" type="search" placeholder="Filter…" value={filter} onChange={(e) => setFilter(e.target.value)} />}
          </div>
          <div className="olinks">
            {(all ? instances : instances.slice(0, 40)).map((i) => <Link key={i.id} term={i} onOpen={onOpen} />)}
          </div>
          {instances.length > 40 && <button className="link-btn" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${instances.length}`}</button>}
        </section>
      )}

      {term.usage && (
        <section className="osub">
          <h4>Use in the knowledge base <span className="muted">· {term.usage.count} statement{term.usage.count === 1 ? "" : "s"}</span></h4>
          {term.usage.examples.length > 0 && (
            <table className="otable">
              <tbody>
                {term.usage.examples.map((x, i) => (
                  <tr key={i}><td><Link term={x.subject} onOpen={onOpen} /></td><td className="muted">{term.label}</td><td><ExprView e={x.object} onOpen={onOpen} /></td></tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {(term.referenced_by ?? []).length > 0 && (
        <section className="osub">
          <h4>Referenced by</h4>
          <dl className="orows">
            {term.referenced_by!.map((r) => (
              <Row key={r.property.id} title={`${r.property.label} (from)`}><Links items={r.subjects.slice(0, 30)} onOpen={onOpen} />{r.subjects.length > 30 && <span className="muted"> +{r.subjects.length - 30}</span>}</Row>
            ))}
          </dl>
        </section>
      )}

      <details className="osub osparql">
        <summary>Query it with SPARQL</summary>
        <pre>{sparql}</pre>
        <Copy text={sparql} />
      </details>
    </article>
  );
}

// ---- the page ---------------------------------------------------------------------------------

type Tab = "classes" | "object" | "datatype" | "annotation";

export default function OntologyEntry({ initial }: { initial: string | null }) {
  const [view, setView] = useState<View>("core");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [terms, setTerms] = useState<ListedTerm[]>([]);
  const [current, setCurrent] = useState<string | null>(initial);
  const [term, setTerm] = useState<Term | null>(null);
  const [tab, setTab] = useState<Tab>("classes");
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<ListedTerm[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showGraph, setShowGraph] = useState(true);
  // the terms visited in this page, for the Back button (null = the overview)
  const [trail, setTrail] = useState<(string | null)[]>([]);
  const goingBack = useRef(false);

  useEffect(() => {
    getOverview(view).then(setOverview).catch((e) => setError(String(e)));
    getTerms(view).then(setTerms).catch(() => setTerms([]));
  }, [view]);

  // the term follows the address (#/ontology/<id>), so the browser's back button works
  useEffect(() => {
    const onHash = () => {
      const match = window.location.hash.match(/^#\/ontology\/?(.*)$/);
      if (match) setCurrent(match[1] ? decodeURIComponent(match[1]) : null);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    if (!current) { setTerm(null); return; }
    let cancelled = false;
    getTerm(current).then((t) => { if (!cancelled) { setTerm(t); setError(null); } })
      .catch(() => { if (!cancelled) setError(`No term “${current}” in the ontology.`); });
    return () => { cancelled = true; };
  }, [current]);

  useEffect(() => {
    const text = query.trim();
    if (text.length < 2) { setFound(null); return; }
    const timer = setTimeout(() => searchTerms(text).then(setFound).catch(() => setFound([])), 180);
    return () => clearTimeout(timer);
  }, [query]);

  function open(id: string | null) {
    if (id === current) return;
    if (!goingBack.current) setTrail((t) => [...t.slice(-30), current]);
    goingBack.current = false;
    window.location.hash = id ? `/ontology/${encodeURIComponent(id)}` : "/ontology";
    setCurrent(id);
    document.querySelector(".obrowser")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function back() {
    if (!trail.length) return;
    const previous = trail[trail.length - 1];
    setTrail(trail.slice(0, -1));
    goingBack.current = true;
    open(previous);
  }

  const labelOf = (id: string | null) =>
    id === null ? "overview" : terms.find((t) => t.id === id)?.label ?? (term?.id === id ? term.label : id.replace(/^[a-z]+:/, ""));

  const trees = useMemo(() => ({
    object: propertyTree(terms, "object"),
    datatype: propertyTree(terms, "datatype"),
    annotation: propertyTree(terms, "annotation"),
  }), [terms]);

  // The term to show selected in the side list: the current one, or for an individual its class.
  // The list moves to its tab and opens its branch; a search that does not hold it is cleared.
  const pick = useMemo(() => {
    if (!current || !overview) return null;
    const forest: [Tab, TreeNode[]][] = [["classes", overview.hierarchy], ["object", trees.object], ["datatype", trees.datatype], ["annotation", trees.annotation]];
    const candidates = [current, ...(term?.id === current && term.kind === "individual" ? term.types.map((t) => t.id) : [])];
    for (const id of candidates) {
      for (const [tab, nodes] of forest) {
        const path = pathTo(nodes, id);
        if (path) return { id, tab, path };
      }
    }
    return null;
  }, [current, term, overview, trees]);
  const listBox = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!pick) return;
    setTab(pick.tab);
    if (found && !found.some((t) => t.id === current)) setQuery("");
    // once the branch is open, bring the row into view inside the list (not the page)
    const timer = setTimeout(() => {
      const box = listBox.current;
      const row = box?.querySelector<HTMLElement>(".otree-row.on, .olist-item.on");
      if (!box || !row) return;
      const top = row.offsetTop - box.offsetTop, bottom = top + row.offsetHeight;
      if (top < box.scrollTop || bottom > box.scrollTop + box.clientHeight) box.scrollTop = top - box.clientHeight / 3;
    }, 60);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pick?.id, pick?.tab, pick?.path.join("|")]);
  const expand = pick?.path ?? [];
  const selectedInList = pick?.id ?? current;

  const o = overview;
  const licence = o?.license ? LICENCES[o.license] ?? o.license : null;
  const prefixes = o ? o.namespaces.map((n) => `PREFIX ${n.prefix}: <${n.namespace}>`).join("\n") : "";

  return (
    <div className="oentry">
      <EntryHero
        kicker="The AIO ontology"
        title={o ? `${o.title} ${o.version ?? ""}` : "AIO ontology"}
        lead={o?.description ?? "The knowledge model behind the portal: water challenges, processes, modelling methods, software and data."}
        aside={o && <span className="ehero-chip">{o.counts.triples.toLocaleString()} asserted triples</span>}
      />
      {error && <p className="error">{error}</p>}

      {o && (
        <section className="panel ometa">
          <div className="oviews" role="tablist" aria-label="Modules of the ontology">
            {VIEWS.map((v) => {
              const info = o.modules.find((m) => m.key === v.id);
              return (
                <button key={v.id} role="tab" aria-selected={view === v.id} className={`oview oview-${v.id}${view === v.id ? " on" : ""}`}
                        onClick={() => { setView(v.id); setTab("classes"); setQuery(""); open(null); }} title={v.note}>
                  <span className="oview-name">{v.name}</span>
                  <span className="oview-sub">{v.id === "all" ? "core + extensions" : `${v.prefix}: · ${info?.counts.class ?? 0} classes`}</span>
                </button>
              );
            })}
          </div>
          <p className="oview-note">{VIEW[view].note}{view !== "core" && view !== "all" && o.imports.length > 0 && <> Imports {o.imports.map((i, n) => <span key={i}>{n > 0 && " and "}<code>{i}</code></span>)}.</>}</p>
          <dl className="ometa-grid">
            <div><dt>Ontology IRI</dt><dd><code>{o.iri}</code> <Copy text={o.iri} /></dd></div>
            <div><dt>Version IRI</dt><dd><code>{o.version_iri ?? "—"}</code></dd></div>
            <div><dt>Prefix</dt><dd><code>{o.prefix}: &lt;{o.namespace}&gt;</code></dd></div>
            <div><dt>Version</dt><dd>{o.version ?? "—"}{o.modified && <span className="muted"> · modified {o.modified}</span>}</dd></div>
            <div><dt>Licence</dt><dd>{o.license ? <a href={o.license} target="_blank" rel="noreferrer">{licence}</a> : "—"}</dd></div>
            <div><dt>Download {view === "all" ? "every module" : "this module"}</dt><dd className="odownloads">
              {FORMATS.map((f) => <a key={f.id} className="odl" href={exportUrl(f.id, view)} title={`${VIEW[view].name} as ${f.label}`}>{f.label}</a>)}
              {view !== "all" && <a className="odl odl-all" href={exportUrl("ttl", "schema")} title="Classes and properties of every module, without individuals, as Turtle">All schemas (.ttl)</a>}
            </dd></div>
          </dl>
          <div className="ocounts">
            {([["classes", o.counts.classes, "classes"], ["object", o.counts.object_properties, "object properties"],
               ["datatype", o.counts.datatype_properties, "datatype properties"], ["annotation", o.counts.annotation_properties, "annotation properties"]] as [Tab, number, string][])
              .map(([id, n, label]) => (
                <button key={id} className={`ocount${tab === id ? " on" : ""}`} onClick={() => { setTab(id); setQuery(""); }}>
                  <strong>{n}</strong><span>{label}</span>
                </button>
              ))}
            <div className="ocount ocount-static"><strong>{o.counts.individuals}</strong><span>individuals</span></div>
          </div>
        </section>
      )}

      {o && (
        <section className="panel ograph">
          <div className="ograph-head">
            <h3>{o.module === "core" ? "The semantic architecture: four axes and how they relate" : o.module === "all" ? "All modules and how they relate" : `${o.title}: its classes and what they build on`}</h3>
            <button className="btn btn-quiet" onClick={() => setShowGraph(!showGraph)}>{showGraph ? "Hide the graph" : "Show the graph"}</button>
          </div>
          {showGraph && <ModuleDiagram overview={o} onOpen={open} selected={current} />}
        </section>
      )}

      <div className="obrowser">
        <aside className="oside">
          <input className="ofind" type="search" placeholder="Search classes, properties, individuals…" value={query} onChange={(e) => setQuery(e.target.value)} />
          {found ? (
            <div className="olist" ref={listBox}>
              <div className="olist-head">{found.length} result{found.length === 1 ? "" : "s"}</div>
              {found.map((t) => (
                <button key={t.id} className={`olist-item${current === t.id ? " on" : ""}`} onClick={() => open(t.id)} title={t.definition ?? undefined}>
                  <Badge kind={t.kind} /> <span>{t.label}</span>{t.module && t.module !== "core" && <span className="omodtag">{VIEW[t.module].short}</span>}
                </button>
              ))}
            </div>
          ) : (
            <>
              <div className="otabs" role="tablist">
                {([["classes", "Classes"], ["object", "Object p."], ["datatype", "Data p."], ["annotation", "Annot."]] as [Tab, string][]).map(([id, label]) => (
                  <button key={id} role="tab" aria-selected={tab === id} className={`otab${tab === id ? " on" : ""}`} onClick={() => setTab(id)}>{label}</button>
                ))}
              </div>
              <div className="olist" ref={listBox}>
                {tab === "classes" && o && (() => {
                  const axes = o.hierarchy.filter((h) => h.group === "axis");
                  const descriptors = o.hierarchy.filter((h) => h.group === "descriptor");
                  const extension = o.hierarchy.filter((h) => h.group === "extension");
                  return (
                    <>
                      {axes.length > 0 && <div className="otree-group">The four axes</div>}
                      {axes.length > 0 && <Tree nodes={axes} current={selectedInList} onOpen={open} expand={expand} />}
                      {extension.length > 0 && <div className="otree-group">{view === "all" ? "Extensions" : VIEW[view].name}</div>}
                      {extension.length > 0 && <Tree nodes={extension} current={selectedInList} onOpen={open} expand={expand} />}
                      {descriptors.length > 0 && <div className="otree-group">Descriptors (value sets)</div>}
                      {descriptors.length > 0 && <Tree nodes={descriptors} current={selectedInList} onOpen={open} expand={expand} />}
                    </>
                  );
                })()}
                {tab !== "classes" && <Tree nodes={trees[tab]} current={selectedInList} onOpen={open} expand={expand} />}
              </div>
            </>
          )}
          <button className={`olist-item ohome${current ? "" : " on"}`} onClick={() => open(null)}>◎ Overview of {view === "all" ? "the ontology" : VIEW[view].name.toLowerCase()}</button>
        </aside>

        <main className="omain">
          {(trail.length > 0 || current) && (
            <div className="onav">
              <button className="btn" onClick={back} disabled={!trail.length}>Back</button>
              {trail.length > 0 && <span className="muted">to {labelOf(trail[trail.length - 1])}</span>}
              <span className="onav-trail">
                {trail.slice(-4).map((id, i) => (
                  <span key={i} className="onav-step">{labelOf(id)}</span>
                ))}
                {current && <span className="onav-step on">{labelOf(current)}</span>}
              </span>
              {current && <button className="link-btn" onClick={() => open(null)}>Overview</button>}
            </div>
          )}
          {current && term && term.id === current && <TermView key={term.id} term={term} onOpen={open} />}
          {current && (!term || term.id !== current) && !error && <p className="muted">Loading…</p>}

          {!current && o && (
            <>
              <section className="osection">
                <h3>{o.module === "core" ? "Axes and descriptors" : "Classes"}</h3>
                <div className="omodules">
                  {[...o.hierarchy].sort((a, b) => (b.total ?? 0) - (a.total ?? 0)).map((m) => {
                    const def = terms.find((t) => t.id === m.id)?.definition;
                    return (
                      <button key={m.id} className="omodule" onClick={() => open(m.id)}>
                        <span className="omodule-head"><strong>{m.label}</strong><span className="muted">{m.total} ind.</span></span>
                        {def && <span className="omodule-def">{def}</span>}
                        {m.children.length > 0 && <span className="omodule-kids">{m.children.map((c) => c.label).join(" · ")}</span>}
                      </button>
                    );
                  })}
                </div>
              </section>
              {(o.reused.length > 0 || o.alignments.length > 0) && (
                <section className="osection">
                  <h3>How AIO links to other ontologies</h3>
                  <LinkMap overview={o} />
                  {o.reused.length > 0 && (
                    <>
                      <h4 className="osub-title">Terms reused from other vocabularies <span className="muted">· used with their original IRI</span></h4>
                      <p className="muted small">AIO does not redefine what standard vocabularies already define: a dataset is a <code>dcat:Dataset</code>, a publisher a <code>foaf:Organization</code>, a unit a QUDT unit. Click a term to see how AIO uses it.</p>
                      <ReusedTable groups={o.reused} onOpen={open} />
                    </>
                  )}
                </section>
              )}
              {o.alignments.length > 0 && (
                <section className="osection">
                  <h3>Alignments to external vocabularies <span className="muted">· {o.alignments.reduce((n, g) => n + g.count, 0)} mappings</span></h3>
                  <p className="muted small">External terms are referenced by IRI with their label and source (MIREOT style): none of these ontologies is imported, and SKOS mappings do not change the reasoning.</p>
                  <AlignmentTable groups={o.alignments} onOpen={open} />
                </section>
              )}
              <section className="osection ouse">
                <div>
                  <h3>Namespaces</h3>
                  <table className="otable">
                    <tbody>
                      {o.namespaces.map((n) => <tr key={n.prefix}><td><code>{n.prefix}</code></td><td><code>{n.namespace}</code></td><td className="muted">{n.uses.toLocaleString()}</td></tr>)}
                    </tbody>
                  </table>
                </div>
                <div>
                  <h3>Use it</h3>
                  <p className="muted">Every term has a stable IRI under <code>{o.namespace}</code>. Declare the prefixes, then query the portal's knowledge graph:</p>
                  <pre className="opre">{`${prefixes}\n\nSELECT ?challenge ?process WHERE {\n  ?challenge a aio:WaterChallenge ;\n             aio:hasPrimaryProcess ?process .\n}`}</pre>
                  <p className="muted small">Cite as: {o.title}, version {o.version}{o.modified ? ` (${o.modified})` : ""}. {o.iri}{licence ? `. Licence ${licence}.` : ""}</p>
                </div>
              </section>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
