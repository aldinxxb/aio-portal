import type { Chain, ChainStep, DataState, Ref , Module } from "../api";
import Def from "./Def";

const name = (item: Ref) => item.label ?? item.id;
const names = (items: Ref[]) => items.map(name).join(", ");

// How a variable is obtained, as a mark and a few words.
const STATE: Record<DataState, { mark: string; text: string; css: string }> = {
  internal: { mark: "↻", text: "from another step", css: "pill-internal" },
  have: { mark: "✓", text: "you have it", css: "pill-hit" },
  open_data: { mark: "◎", text: "open data", css: "pill-open" },
  missing: { mark: "⚠", text: "no source", css: "pill-warn" },
};

function StatePill({ item }: { item: Ref & { state: DataState } }) {
  const state = STATE[item.state];
  return (
    <span className={`pill ${state.css}`} title={state.text}>
      {state.mark} {name(item)}
    </span>
  );
}

function Row({ title, children }: { title: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="fact">
      <dt>{title}</dt>
      <dd>{children}</dd>
    </div>
  );
}

const plain = (items: Ref[]) =>
  items.length === 0 ? (
    <span className="muted">none recorded</span>
  ) : (
    items.map((i) => (
      <span key={i.id} className="pill">
        {name(i)}
      </span>
    ))
  );

// One step of the chain. Closed: its role, method and software. Open: its parameters,
// inputs and outputs.
// How a method runs in its software: module name, time step, computational unit and size.
export function ModuleLine({ module }: { module: Module }) {
  return (
    <div className="module-line">
      <strong>{module.name}</strong> <span className="muted">in {name(module.software)}</span>
      <span className="module-facts">
        <span title="usual time step in this software">⏱ {module.time_step}</span>
        <span title="computational unit">◫ {module.spatial_unit && /\bHRU/.test(module.spatial_unit) ? <Def k="hru">{module.spatial_unit}</Def> : module.spatial_unit}</span>
        <span title="usual spatial resolution">▦ {module.resolution}</span>
      </span>
    </div>
  );
}

function Step({ step }: { step: ChainStep }) {
  const d = step.detail;
  return (
    <details className={`chain-step${step.issue ? " has-issue" : ""}`}>
      <summary>
        <span className="chain-order">{step.order}</span>
        <span className="chain-method">{name(step.method)}</span>
        <span className="chain-role">{names(step.roles)}</span>
        {step.software && <span className="tag tag-info">{name(step.software)}</span>}
        {step.module && (
          <span className="module-chip" title={step.module.name ?? ""}>
            ⏱ {step.module.time_step} · ▦ {step.module.resolution}
          </span>
        )}
        {step.issue && <span className="tag tag-hard">to check</span>}
      </summary>

      <div className="chain-step-body">
        {step.module && <ModuleLine module={step.module} />}
        {step.issue && <p className="error">{step.issue}</p>}
        {step.alternatives.length > 0 && (
          <p className="result-note">
            Could be replaced by:{" "}
            {step.alternatives
              .map((a) => `${name(a)}${a.same_software ? " (same software)" : ""}`)
              .join(", ")}
          </p>
        )}
        <dl className="facts">
          <Row title="Inputs">
            {d.mandatory_inputs.length === 0 && <span className="muted">none recorded</span>}
            {d.mandatory_inputs.map((i) => (
              <StatePill key={i.id} item={i} />
            ))}
          </Row>
          {d.optional_inputs.length > 0 && <Row title="Optional inputs">{plain(d.optional_inputs)}</Row>}
          {d.initial_conditions.length > 0 && (
            <Row title="Initial state">
              {plain(d.initial_conditions)}
              <span className="muted">from a warm-up run or an observed snapshot</span>
            </Row>
          )}
          <Row title="Physical parameters">
            {d.physical_parameters.length === 0 && <span className="muted">none recorded</span>}
            {d.physical_parameters.map((i) => (
              <StatePill key={i.id} item={i} />
            ))}
          </Row>
          <Row title="Calibration parameters">{plain(d.calibration_parameters)}</Row>
          <Row title="Outputs">{plain(d.outputs)}</Row>
          <Row title="Time steps">
            {d.supports_time_steps.length === 0 && <span className="muted">not recorded</span>}
            {d.supports_time_steps.map((s) => (
              <span key={s.id} className="pill">
                {name(s)}
                {d.typical_time_steps.some((t) => t.id === s.id) ? " (typical)" : ""}
              </span>
            ))}
          </Row>
        </dl>
      </div>
    </details>
  );
}

type CardProps = {
  chain: Chain;
  open: boolean;
  onAdjust?: (chain: Chain) => void;   // open this workflow's diagnosis (Modeling Approach)
  best?: string[];                     // the best match: why, in a few words
  compare?: { on: boolean; full: boolean; onToggle: () => void };   // ticked for the side-by-side comparison
};

const NATURES: { id: "forcing" | "boundary" | "static"; title: string }[] = [
  { id: "forcing", title: "Forcing" },
  { id: "boundary", title: "Boundary conditions" },
  { id: "static", title: "Static description" },
];

// One recommended workflow. Closed: its name, software, verdict and two small meters
// (processes covered, data available). Open: the essential steps on the left, what the
// workflow needs and gives on the right, the optional components, then the action.
export default function ChainCard({ chain, open, onAdjust, best, compare }: CardProps) {
  const runnable = chain.status === "runnable";
  const count = (state: DataState) => chain.inputs.filter((i) => i.state === state).length;
  const total = chain.inputs.length;
  const reachable = count("have") + count("open_data");

  return (
    <details className={`chain wf ${runnable ? "is-direct" : "is-complement"}${best ? " is-best" : ""}`} open={open}>
      <summary className="wf-head">
        <div className="wf-name">
          {best && (
            <span className="wf-best">
              <span className="wf-best-badge">★ Best match</span>
              {best.length > 0 && <span className="wf-best-why">{best.join(" · ")}</span>}
            </span>
          )}
          <span className="chain-title">{chain.label}</span>
          <span className="wf-software">
            {chain.software.map((s) => (
              <span key={s.id} className="wf-soft" title={s.open ? "open source" : s.free ? "free of charge" : "commercial"}>
                {name(s)}<i className={`wf-lic ${s.open ? "open" : s.free ? "free" : "paid"}`} />
              </span>
            ))}
            {chain.software.length > 1 && <span className="muted">· <Def k="coupling">coupled</Def> ({chain.coupling ? name(chain.coupling) : "two software"})</span>}
          </span>
        </div>
        {compare && (
          <label className={`wf-compare${compare.on ? " on" : ""}`} title={compare.full && !compare.on ? "Three workflows at most" : "Compare it side by side with others"}>
            <input type="checkbox" checked={compare.on} disabled={compare.full && !compare.on} onChange={compare.onToggle} />
            compare
          </label>
        )}
        <div className="wf-tags">
          <span className={`tag ${runnable ? "tag-direct" : "tag-complement"}`}>{runnable ? "ready to run" : "to check"}</span>
          <span className={`tag ${chain.kind === "reference" ? "tag-soft" : "tag-info"}`}>
            {chain.kind === "reference" ? <Def k="standard">standard practice</Def> : <Def k="generated">possible combination</Def>}
          </span>
        </div>
        <div className="wf-meters">
          {chain.coverage !== null && (
            <span className="wf-meter" title="Share of the main processes of the challenge it models">
              <span className="wf-meter-label">processes</span>
              <span className="wf-bar"><i style={{ width: `${Math.round(chain.coverage * 100)}%` }} /></span>
              <span className="wf-meter-value">{Math.round(chain.coverage * 100)}%</span>
            </span>
          )}
          <span className="wf-meter" title="Required data you have or can get as open data">
            <span className="wf-meter-label">data</span>
            <span className="wf-bar data"><i style={{ width: `${total ? Math.round((reachable / total) * 100) : 100}%` }} /></span>
            <span className="wf-meter-value">{reachable}/{total}</span>
          </span>
        </div>
      </summary>

      <div className="chain-body">
        {(chain.note || chain.reasons.length > 0) && (
          <div className="wf-notes">
            {chain.note && <p className="result-note">{chain.note}</p>}
            {chain.reasons.map((reason) => <p key={reason} className="error">{reason}</p>)}
          </div>
        )}

        <div className="wf-grid">
          <section>
            <h4 className="wf-sub">Essential steps <span className="muted">· click one for its inputs, parameters, outputs and module</span></h4>
            <div className="chain-steps">
              {chain.steps.map((step) => <Step key={step.method.id} step={step} />)}
            </div>
            {chain.optional_steps.length > 0 && (
              <div className="optional-steps">
                <div className="optional-title">
                  Optional components <span className="muted">· left out at first, their effect can be neglected</span>
                </div>
                {chain.optional_steps.map((o) => (
                  <div key={o.method.id} className="optional-row">
                    <span className="flow-chip flow-optional">＋ {name(o.method)}</span>
                    <span className="muted">as {names(o.roles)}{o.software ? ` · ${name(o.software)}` : ""}</span>
                    <span>{o.adds_processes.length > 0 ? <>adds <strong>{names(o.adds_processes)}</strong></> : "refines a process already modelled"}</span>
                    {o.module && <span className="module-chip">⏱ {o.module.time_step} · ▦ {o.module.resolution}</span>}
                  </div>
                ))}
              </div>
            )}
          </section>

          <section>
            <h4 className="wf-sub">What it needs</h4>
            <div className="wf-counts">
              <span className="pill pill-hit">✓ {count("have")} you have</span>
              <span className="pill pill-open">◎ {count("open_data")} <Def k="opendata">open data</Def></span>
              <span className={`pill${count("missing") ? " pill-warn" : ""}`}>⚠ {count("missing")} without a source</span>
            </div>
            <dl className="facts">
              {NATURES.map((n) => {
                const items = chain.inputs.filter((i) => (i.nature ?? (i.kind === "parameter" ? "static" : "forcing")) === n.id);
                return items.length ? (
                  <Row key={n.id} title={<Def k={n.id}>{n.title}</Def>}>{items.map((i) => <StatePill key={i.id} item={i} />)}</Row>
                ) : null;
              })}
              {chain.inputs.length === 0 && <Row title="Inputs"><span className="muted">nothing to bring</span></Row>}
              {chain.initial_conditions.length > 0 && (
                <Row title={<Def k="initial" />}>
                  {plain(chain.initial_conditions)}
                  <span className="muted">warm-up run or observed snapshot</span>
                </Row>
              )}
              {chain.calibration.needed && (
                <Row title={<Def k="calibration" />}>
                  <span className={chain.calibration.ok ? "reason-pass" : "reason-fail"}>
                    {chain.calibration.ok ? "✓ measured data exists for " : "✗ no measured data for "}
                    {names(chain.calibration.against)}
                  </span>
                </Row>
              )}
            </dl>
            <h4 className="wf-sub">What it gives</h4>
            <dl className="facts">
              <Row title="Delivers">{plain(chain.delivers)}</Row>
              <Row title="Processes">{plain(chain.covers)}</Row>
            </dl>
          </section>
        </div>

        {onAdjust && (
          <div className="wf-action">
            <button className="btn btn-primary" onClick={() => onAdjust(chain)}>Check this workflow for my study</button>
            <span className="muted">
              How well it fits, what is missing, and the parts you can change, add or leave out.
              Back brings you here again.
            </span>
          </div>
        )}
      </div>
    </details>
  );
}
