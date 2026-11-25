import { useMemo, useState } from "react";
import type { Chain, Ref } from "../api";
import ChainCard from "./ChainCard";
import Def from "./Def";
import { count, toFind } from "../workflowRank";

// The recommended workflows, as a list the user can act on (shared by both results pages):
//   - the best match is marked, with why, in a few words taken from its own facts
//   - the list can be sorted by what matters to the user
//   - up to three workflows can be compared side by side

const name = (item: Ref) => item.label ?? item.id;
const names = (items: Ref[]) => items.map(name).join(", ");

type Sort = "best" | "data" | "processes" | "software";
const SORTS: { id: Sort; label: string }[] = [
  { id: "best", label: "best match" },
  { id: "data", label: "least data to find" },
  { id: "processes", label: "most processes covered" },
  { id: "software", label: "single software first" },
];

function sorted(chains: Chain[], sort: Sort): Chain[] {
  const order = new Map(chains.map((c, i) => [c.id, i]));
  const by = (f: (c: Chain) => number) => [...chains].sort((a, b) => f(a) - f(b) || order.get(a.id)! - order.get(b.id)!);
  if (sort === "data") return by((c) => toFind(c));
  if (sort === "processes") return by((c) => -(c.coverage ?? 0));
  if (sort === "software") return by((c) => c.software.length);
  return chains;
}

function Compare({ chains, onClear }: { chains: Chain[]; onClear: () => void }) {
  const rows: [React.ReactNode, (c: Chain) => React.ReactNode][] = [
    ["Software", (c) => c.software.map((s) => `${name(s)} (${s.open ? "open source" : s.free ? "free" : "commercial"})`).join(" + ")],
    ["Status", (c) => (c.status === "runnable" ? "ready to run" : "to check")],
    ["Kind", (c) => (c.kind === "reference" ? "standard practice" : "combination built by the portal")],
    ["Main processes", (c) => (c.coverage === null ? "–" : `${Math.round(c.coverage * 100)}%`)],
    ["Data", (c) => `${count(c, "have")} in hand · ${count(c, "open_data")} open data · ${count(c, "missing")} without a source`],
    ["To fetch", (c) => names(c.inputs.filter((i) => i.state === "open_data")) || "nothing"],
    ["Without a source", (c) => names(c.inputs.filter((i) => i.state === "missing")) || "nothing"],
    ["Steps", (c) => c.steps.map((s) => name(s.method)).join(" → ")],
    [<Def key="timestep" k="timestep" />, (c) => [...new Set(c.steps.map((s) => s.module?.time_step).filter(Boolean))].join(", ") || "–"],
    [<Def key="calibration" k="calibration" />, (c) => (!c.calibration.needed ? "not needed" : c.calibration.ok ? `measured data exists (${names(c.calibration.against)})` : `no measured data for ${names(c.calibration.against)}`)],
    ["Delivers", (c) => names(c.delivers) || "–"],
  ];
  return (
    <div className="wcompare">
      <div className="wcompare-head">
        <strong>Comparing {chains.length} workflows</strong>
        <button className="link-btn" onClick={onClear}>Clear the comparison</button>
      </div>
      <div className="wcompare-scroll">
        <table className="wcompare-table">
          <thead>
            <tr><th />{chains.map((c) => <th key={c.id}>{c.label}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map(([label, cell], i) => (
              <tr key={i}><th scope="row">{label}</th>{chains.map((c) => <td key={c.id}>{cell(c)}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function WorkflowList({ chains, bestId, why, onAdjust, openFirst = true }: {
  chains: Chain[];
  bestId: string | null;          // the best match (it may be in another list of the page)
  why: string[];                  // why it is the best match
  onAdjust?: (chain: Chain) => void;
  openFirst?: boolean;
}) {
  const [sort, setSort] = useState<Sort>("best");
  const [picked, setPicked] = useState<string[]>([]);
  const shown = useMemo(() => sorted(chains, sort), [chains, sort]);
  const comparing = chains.filter((c) => picked.includes(c.id));

  function toggle(id: string) {
    setPicked((now) => (now.includes(id) ? now.filter((x) => x !== id) : now.length >= 3 ? now : [...now, id]));
  }

  if (chains.length === 0) return null;
  return (
    <div className="wlist">
      {chains.length > 1 && (
        <div className="wlist-tools">
          <label className="inline-field">
            <span>Sort by</span>
            <select className="select" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
              {SORTS.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
          </label>
          <span className="muted">
            {picked.length === 0 ? "Tick “compare” on two or three workflows to see them side by side."
              : picked.length === 1 ? "Tick one or two more to compare." : picked.length === 3 ? "Three at most." : ""}
          </span>
        </div>
      )}
      {comparing.length >= 2 && <Compare chains={comparing} onClear={() => setPicked([])} />}
      {shown.map((chain, index) => (
        <ChainCard key={chain.id} chain={chain} open={openFirst && index === 0} onAdjust={onAdjust}
                   best={chain.id === bestId ? why : undefined}
                   compare={chains.length > 1 ? { on: picked.includes(chain.id), full: picked.length >= 3, onToggle: () => toggle(chain.id) } : undefined} />
      ))}
    </div>
  );
}
