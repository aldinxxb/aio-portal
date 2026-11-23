import { useEffect, useMemo, useState } from "react";
import { getTerm, type Expr, type Term } from "../ontologyApi";
import type { Action, Component, DataRow, Diagnosis, Improvement, Target } from "../setupApi";
import { derivationText, KIND, NATURE, name, names, sourceOf, STATUS } from "../setupLabels";
import SetupDiagram from "./SetupDiagram";

// The Diagnosis page, read from top to bottom like a report:
//   1. the study the user described          (what the set-up is judged for)
//   2. the verdict                           (one score, one sentence, the numbers that matter)
//   3. the set-up as a picture               (data -> methods -> results)
//   4. tabs, one thing at a time             improvements | expected outputs | workflow summary
// The picture keeps its own size on the left; the study, the verdict and the checks sit beside it.
// Improvements are grouped by what is missing; only the best option of a group is shown
// until the user asks for the others. A declined suggestion is hidden, and can be restored.

const PRIORITY: Record<Action["group"], { text: string; css: string; rank: number }> = {
  fix_first: { text: "fix first", css: "tag-hard", rank: 0 },
  recommended: { text: "recommended", css: "tag-soft", rank: 1 },
  optional: { text: "optional", css: "tag-info", rank: 2 },
};
const TARGET: Record<Target["type"], string> = {
  data: "Missing data",
  role: "Missing component",
  process: "Missing process",
  output: "Expected output not delivered",
  method: "Method to reconsider",
  workflow: "Whole workflow",
  component: "Optional component",
};
const OUTPUT_STATUS = {
  delivered: { text: "delivered", css: "pill-hit" },
  needs_combination: { text: "needs another method", css: "pill-warn" },
  unreachable: { text: "out of reach", css: "pill-warn" },
};
const PATH: Record<Action["path"], string> = {
  more_data: "more data",
  finer_data: "finer data",
  combine: "add a method",
  replace: "replace",
};

type ActionGroup = { key: string; target: Target; priority: Action["group"]; actions: Action[] };
type Tab = "improve" | "outputs" | "checks" | "summary";

const isLink = (url: string | null | undefined): url is string => !!url && /^https?:\/\//.test(url);

// Where a piece of data comes from, pointing to it: the dataset page, or how to derive it.
function Source({ row }: { row: DataRow }) {
  const link = (d: { id: string; label: string | null; url: string | null }) =>
    isLink(d.url) ? <a key={d.id} href={d.url} target="_blank" rel="noreferrer">{name(d)} ↗</a> : <span key={d.id}>{name(d)}</span>;
  const step = row.step_ref ? ` (${name(row.step_ref)})` : "";
  return (
    <>
      <span className={`pill ${STATUS[row.status].css}`}>{STATUS[row.status].text}</span>
      {row.status === "in_hand" && (
        <div className="muted">{row.dataset ? <>from {link(row.dataset)}{step}</> : `your own data${step}`}</div>
      )}
      {row.status !== "in_hand" && row.datasets.length > 0 && (
        <div className="source-line">
          <span className="muted">Dataset:</span>{" "}
          {row.datasets.slice(0, 3).map((d, i) => <span key={d.id}>{i > 0 && ", "}{link(d)}</span>)}
          {row.datasets.length > 3 && <span className="muted"> +{row.datasets.length - 3} more</span>}
        </div>
      )}
      {row.status !== "in_hand" && row.derivations.map((derivation, i) => (
        <div key={i} className="source-line">
          <span className="muted">{row.datasets.length ? "Or derive it" : "Derive it"}</span> from{" "}
          {derivation.from.map((input, j) => (
            <span key={input.id}>
              {j > 0 && " + "}
              <strong>{name(input)}</strong>
              <span className="muted"> ({input.datasets ? `${input.datasets} dataset${input.datasets > 1 ? "s" : ""}` : "no open dataset"})</span>
            </span>
          ))}
          {derivation.how && <span className="how"> · {derivation.how}</span>}
        </div>
      ))}
      {row.status !== "in_hand" && row.datasets.length === 0 && row.derivations.length === 0 && (
        <div className="muted">{sourceOf(row)}</div>
      )}
    </>
  );
}

const groupId = (t: Target) => `group-${t.type}-${t.id}`;

function groupByTarget(actions: Action[]): ActionGroup[] {
  const groups = new Map<string, ActionGroup>();
  for (const action of actions) {
    const t = action.target;
    const key = `${t.type}:${t.id}:${t.use ?? ""}`;
    const group = groups.get(key);
    if (group) {
      group.actions.push(action);
      if (PRIORITY[action.group].rank < PRIORITY[group.priority].rank) group.priority = action.group;
    } else {
      groups.set(key, { key, target: t, priority: action.group, actions: [action] });
    }
  }
  return [...groups.values()].sort((a, b) => PRIORITY[a.priority].rank - PRIORITY[b.priority].rank);
}

function targetTitle(t: Target): string {
  if (t.type === "data") return `${TARGET.data} · ${t.use === "calibration" ? KIND.calibration : NATURE[t.nature ?? "forcing"]}`;
  return TARGET[t.type];
}

// ---- one method in full: what it takes, its parameters, what it gives, how it runs ---------------

const DETAIL_GROUPS: { title: string; help: string; props: { id: string; label: string }[] }[] = [
  { title: "Inputs", help: "the data the method needs", props: [
    { id: "requiresMandatoryInput", label: "required" }, { id: "acceptsOptionalInput", label: "optional" },
    { id: "requiresInitialCondition", label: "initial state" }] },
  { title: "Parameters", help: "values describing the site, or tuned against observations", props: [
    { id: "hasPhysicalParameter", label: "physical" }, { id: "hasCalibrationParameter", label: "calibrated" },
    { id: "isCalibratedAgainst", label: "calibrated against" }] },
  { title: "Outputs", help: "the variables it computes", props: [{ id: "producesOutput", label: "computes" }] },
  { title: "Processes", help: "the hydrological processes it represents", props: [{ id: "modelsProcess", label: "models" }] },
  { title: "How it runs", help: "time step, mode and spatial representation", props: [
    { id: "supportsTimeStep", label: "time steps" }, { id: "hasTypicalTimeStep", label: "typical step" },
    { id: "hasTemporalMode", label: "mode" }, { id: "hasSpatialRepresentation", label: "space" },
    { id: "hasDimensionality", label: "dimensions" }, { id: "hasApplicationScale", label: "scale" }] },
  { title: "Software", help: "where it can be run", props: [{ id: "canBeImplementedIn", label: "available in" }] },
];

function MethodDetails({ id, data, expected }: { id: string; data: DataRow[]; expected: Diagnosis["outputs"] }) {
  const [term, setTerm] = useState<Term | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let cancelled = false;
    getTerm(id).then((t) => { if (!cancelled) setTerm(t); }).catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, [id]);
  if (failed) return <div className="method-details muted">The details of this method could not be read.</div>;
  if (!term) return <div className="method-details muted">Reading the method…</div>;

  const facts = new Map((term.facts ?? []).map((f) => [f.property.id, f.values]));
  const status = new Map(data.map((r) => [r.id, r]));
  const wanted = new Set(expected.flatMap((o) => o.variables.map((v) => v.id)));
  const label = (e: Expr) => ("label" in e ? e.label : "value" in e ? e.value : "");
  const idOf = (e: Expr) => ("id" in e ? e.id : "");

  return (
    <div className="method-details">
      {term.definition && <p className="method-def">{term.definition}</p>}
      <div className="method-grid">
        {DETAIL_GROUPS.map((group) => {
          const rows = group.props.map((p) => ({ ...p, values: facts.get(p.id) ?? [] })).filter((r) => r.values.length);
          if (!rows.length) return null;
          return (
            <div key={group.title} className="method-group">
              <div className="method-group-title" title={group.help}>{group.title}</div>
              {rows.map((row) => (
                <div key={row.id} className="method-row">
                  <span className="method-row-label">{row.label}</span>
                  <span className="method-values">
                    {row.values.map((v, i) => {
                      const ref = status.get(idOf(v));
                      const css = group.title === "Inputs" || group.title === "Parameters"
                        ? ref ? STATUS[ref.status].css : ""
                        : group.title === "Outputs" && wanted.has(idOf(v)) ? "pill-hit" : "";
                      return (
                        <span key={i} className={`pill ${css}`}
                              title={ref ? `${STATUS[ref.status].text} · ${sourceOf(ref)}` : group.title === "Outputs" && wanted.has(idOf(v)) ? "behind an expected output" : undefined}>
                          {label(v)}
                        </span>
                      );
                    })}
                  </span>
                </div>
              ))}
            </div>
          );
        })}
      </div>
      <div className="method-foot">
        <span className="muted">Inputs and parameters are coloured by where their data comes from; outputs behind an expected output are green.</span>
        <a href={`#/ontology/${encodeURIComponent(term.id)}`} target="_blank" rel="noreferrer">Open it in the ontology</a>
      </div>
    </div>
  );
}

function ActionCard({ action, declined, onAccept, onDecline, onRestore }: {
  action: Action;
  declined: boolean;
  onAccept: () => void;
  onDecline: () => void;
  onRestore: () => void;
}) {
  const gain = action.effect.fit_after - action.effect.fit_before;
  const unblocked = action.effect.blocking_before - action.effect.blocking_after;
  return (
    <div className={`action${declined ? " action-declined" : ""}`}>
      <div className="action-main">
        <div className="action-message">{action.message}</div>
        <div className="action-facts">
          <span className="tag tag-info">{PATH[action.path]}</span>
          <span className="muted">effort {action.effort}</span>
          {!action.advice && gain > 0 && <span className="gain">fit +{gain}</span>}
          {!action.advice && unblocked > 0 && <span className="gain">removes {unblocked} blocking issue{unblocked > 1 ? "s" : ""}</span>}
          {action.software && (
            <span>
              <span className={`pill ${action.software.same ? "pill-hit" : action.software.same === false ? "pill-amber" : ""}`}>
                {action.software.same ? "same software" : action.software.same === false ? "another software" : "software"}
              </span>{" "}
              {action.software.software.length ? names(action.software.software) : "none recorded"}
              {action.software.same === false && action.software.current?.length > 0 && (
                <span className="muted"> · yours: {names(action.software.current)}</span>
              )}
            </span>
          )}
        </div>
        {action.contributes.map((c) => (
          <div key={c.method.id} className="contrib">
            <span className="muted">{name(c.method)} contributes</span>
            {c.variables.filter((v) => v.use || action.contributes.length === 1).map((v) => (
              <span key={v.id} className={`pill${v.use ? " pill-key" : ""}`} title={v.use ?? "computed, not needed by this study"}>
                {name(v)}
                {v.new && <sup> new</sup>}
                {v.use && <span className="contrib-use"> → {v.use}</span>}
              </span>
            ))}
          </div>
        ))}
        {action.detail && action.contributes.length === 0 && <div className="muted">{action.detail}</div>}
      </div>
      <div className="action-buttons">
        {declined ? (
          <button className="btn" onClick={onRestore}>Restore</button>
        ) : action.advice ? (
          <>
            <span className="muted">advice</span>
            <button className="btn btn-quiet" onClick={onDecline}>Dismiss</button>
          </>
        ) : (
          <>
            <button className="btn btn-primary" onClick={onAccept}>Accept</button>
            <button className="btn btn-quiet" onClick={onDecline}>Decline</button>
          </>
        )}
      </div>
    </div>
  );
}

// One picture per job, to recognise the components of a chain at a glance.
const ROLE_ICON: Record<string, string> = {
  Role_PET: "☀️", Role_Interception: "🌿", Role_Snow: "❄️", Role_SoilWaterBudget: "🟤",
  Role_ActualET: "♨️", Role_ExcessRainfall: "🌧️", Role_RunoffTransform: "📈", Role_Baseflow: "💧",
  Role_GroundwaterFlow: "🪨", Role_ChannelRouting: "🏞️", Role_Hydraulics: "🌊",
  Role_SedimentTransport: "⏳", Role_Morphology: "⛰️", Role_PollutantLoading: "🧪",
  Role_SoluteTransport: "🧫", Role_HeatTransport: "🌡️",
};

// What is lost when one component of the chain is left out. Shown before the user confirms.
function Losses({ part }: { part: Component }) {
  const lose = part.loses;
  const nothing = lose.processes.length + lose.outputs.length + lose.downstream.length + lose.blocking.length === 0;
  return (
    <div className={`leave-box leave-${part.verdict}`}>
      <div className="leave-title">
        Without {name(part)}
        {part.needed && <span className="pill pill-warn">usual part of this workflow</span>}
      </div>
      {nothing && <div>Nothing the study needs is lost: no process, output or input of another method depends on it.</div>}
      {lose.outputs.length > 0 && (
        <div className="leave-line"><strong>Outputs no longer delivered:</strong> {names(lose.outputs)}</div>
      )}
      {lose.processes.length > 0 && (
        <div className="leave-line">
          <strong>Processes no longer modelled:</strong>{" "}
          {lose.processes.map((p) => `${name(p)}${p.main ? " (a main process of the challenge)" : ""}`).join(", ")}
        </div>
      )}
      {lose.downstream.map((x) => (
        <div key={`${x.method.id}-${x.variable.id}`} className="leave-line">
          <strong>{name(x.method)}</strong> no longer receives <strong>{name(x.variable)}</strong>
          {x.required ? `: it must then be given as ${NATURE[x.nature]} data (${STATUS[x.then]?.text ?? x.then}).`
            : " (an optional input: it runs without it, less precisely)."}
        </div>
      ))}
      {lose.variables.length > 0 && (
        <div className="leave-line muted">No longer computed: {names(lose.variables)}.</div>
      )}
      {lose.blocking.map((message) => (
        <div key={message} className="leave-line reason-fail">{message}</div>
      ))}
      <div className="leave-line muted">
        Fit {part.effect.fit_before} → {part.effect.fit_after}
        {part.same_software.length > 0 && <> · simpler options in the same software: {names(part.same_software)}</>}
      </div>
    </div>
  );
}

export default function SetupDiagnosis({ result, loading, accepted, declined, onAccept, onUndo, onDecline, onRestore, onEdit, onLeaveOut, onPutBack, onSwap, autoAdded = {} }: {
  // methods added automatically to deliver an expected output: method id -> output label
  autoAdded?: Record<string, string>;
  // replace a method by another one of the same software, for the same job
  onSwap: (method: Diagnosis["setup"]["methods"][number], by: Component["alternatives"][number]) => void;
  onLeaveOut: (component: Component) => void;                       // remove a component on purpose
  onPutBack: (method: Diagnosis["setup"]["left_out"][number]) => void;
  result: Improvement;
  loading: boolean;
  accepted: string[];                    // messages of the accepted actions, oldest first
  declined: string[];                    // ids of the declined actions
  onAccept: (action: Action) => void;
  onUndo: () => void;
  onDecline: (ids: string[]) => void;
  onRestore: (ids: string[] | null) => void;   // null: restore everything
  onEdit: (step: number) => void;
}) {
  const [tab, setTab] = useState<Tab>("improve");
  const [expanded, setExpanded] = useState<string[]>([]);      // groups showing every option
  const [showDeclined, setShowDeclined] = useState(false);
  const [copied, setCopied] = useState(false);
  const [leaving, setLeaving] = useState<string | null>(null);   // the component whose losses are shown
  const [details, setDetails] = useState<string | null>(null);      // the method whose details are open
  const [switching, setSwitching] = useState<string | null>(null); // the component whose alternatives are shown

  const d = result.diagnosis;
  const open = result.actions.filter((a) => !declined.includes(a.id));
  const hidden = result.actions.filter((a) => declined.includes(a.id));
  const groups = useMemo(() => groupByTarget(open), [result, declined]);   // eslint-disable-line react-hooks/exhaustive-deps
  const issues = d.checks.filter((c) => c.status !== "ok").length;

  // a red box of the diagram was clicked: show the improvements that supply it
  function jumpTo(target: string) {
    const [type, id] = target.split(":");
    setTab("improve");
    setTimeout(() => {
      const element = document.getElementById(`group-${type}-${id}`) ?? document.getElementById("improvements");
      element?.scrollIntoView({ behavior: "smooth", block: "center" });
      element?.classList.add("flash");
      setTimeout(() => element?.classList.remove("flash"), 1500);
    }, 30);
  }

  // ---- the workflow in plain text (for a report or an e-mail) ----
  function summaryText(): string {
    const s = d.study;
    const lines = [
      `Study: ${name(s.challenge!)} – ${name(s.objective!)}`,
      d.outputs.length ? `Expected outputs: ${d.outputs.map((o) => `${name(o)} (${OUTPUT_STATUS[o.status].text})`).join("; ")}` : "",
      s.output_step ? `Time step of the results: ${name(s.output_step)}` : "",
      `Fit: ${d.fit.score}/100 (${d.fit.label})`,
      "",
      "Chain of methods:",
      ...d.setup.methods.map((m, i) => `  ${i + 1}. ${name(m)} – ${names(m.roles) || "no recorded job"}`),
      "",
      "Data:",
      ...d.data.map((r) => `  - ${name(r)} (${KIND[r.kind]}, ${NATURE[r.nature]}): ${sourceOf(r)}`),
    ];
    return lines.filter((line, i) => line !== "" || lines[i - 1] !== "").join("\n");
  }

  function copySummary() {
    navigator.clipboard?.writeText(summaryText()).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });
  }

  const s = d.study;
  const facts: [string, string][] = [];
  if (s.output_step) facts.push(["Results every", name(s.output_step)]);
  if (s.intent) facts.push(["Decision intent", name(s.intent)]);
  if (s.scenario) facts.push(["Scenario", name(s.scenario)]);
  if (s.entity) facts.push(["Water entity", name(s.entity)]);
  if (s.driver) facts.push([s.driver_assumed ? "Driver (assumed)" : "Driver", name(s.driver)]);
  const software = d.setup.software;

  return (
    <div className={loading ? "is-refreshing" : ""}>
      <div className="diag-top">
        <section className="diag-graph">
          {/* the picture, at its own size */}
      <div className="section-head">
        <h4>Your set-up at a glance</h4>
        <span className="muted">
          {software ? `in ${name(software)} · ` : ""}
          {d.best_template ? `compared with the usual workflow “${name(d.best_template)}”` : ""}
        </span>
      </div>
      <SetupDiagram diagnosis={d} onPick={jumpTo} />

          {/* the checks, at a glance */}
          <div className="side-checks">
            <div className="section-head"><h4>Checks</h4><span className="muted">{issues ? `${issues} to look at` : "all passed"}</span></div>
            {d.checks.map((check) => (
              <div key={check.id} className={`side-check check-${check.status}`} title={check.message}>
                <span className="check-mark">{check.status === "ok" ? "✓" : check.status === "fail" ? "✗" : "!"}</span>
                <span className="side-check-text"><strong>{check.title}</strong><span className="muted">{check.message}</span></span>
              </div>
            ))}
          </div>
        </section>
        <aside className="diag-side">
      {/* 1. the study */}
      <div className="study-card">
        <div className="study-head">
          <span className="target-kind">Your study</span>
          <button className="link-btn" onClick={() => onEdit(1)}>Edit the study</button>
        </div>
        <div className="study-title">
          {name(s.challenge!)} <span className="study-sep">·</span> {name(s.objective!)}
        </div>
        <div className="study-facts">
          {facts.map(([label, value]) => (
            <span key={label} className="study-fact"><span className="muted">{label}</span> {value}</span>
          ))}
        </div>
        <div className="study-outputs">
          <span className="muted">Expected outputs</span>
          {d.outputs.length === 0 && (
            <span className="muted">
              none chosen · <button className="link-btn" onClick={() => onEdit(1)}>choose one</button> to check the set-up delivers it
            </span>
          )}
          {d.outputs.map((o) => (
            <div key={o.id} className="study-output">
              <div>
                <strong>{name(o)}</strong>{" "}
                <span className={`pill ${OUTPUT_STATUS[o.status].css}`}>{OUTPUT_STATUS[o.status].text}</span>
              </div>
              {o.question && <div className="opt-question">{o.question}</div>}
            </div>
          ))}
        </div>
      </div>

      {/* 2. the verdict */}
      <div className={`fit fit-${d.fit.label.replace(" ", "-")}`}>
        <div className="fit-score">{d.fit.score}<span className="fit-of">/100</span></div>
        <div className="fit-text">
          <div className="fit-label">{d.fit.label}</div>
          <div>
            {d.fit.blocking > 0
              ? `${d.fit.blocking} thing${d.fit.blocking > 1 ? "s" : ""} to fix before this set-up can answer the study.`
              : d.fit.warnings > 0
                ? "Nothing blocks the study; some improvements are worth making."
                : "This set-up suits the study."}
          </div>
        </div>
        <div className="fit-counts">
          <span><strong>{d.fit.blocking}</strong> to fix</span>
          <span><strong>{d.fit.warnings}</strong> to improve</span>
          <span><strong>{Math.round(d.coverage.primary * 100)}%</strong> main processes</span>
        </div>
      </div>
      {d.warnings.map((w) => (
        <p key={w} className="group-note">{w}</p>
      ))}
      {accepted.length > 0 && (
        <div className="accepted-bar">
          <span>
            <strong>{accepted.length}</strong> improvement{accepted.length > 1 ? "s" : ""} accepted · last:{" "}
            <span className="muted">{accepted[accepted.length - 1]}</span>
          </span>
          <button className="link-btn" onClick={onUndo}>Undo last</button>
        </div>
      )}

          {/* the data the set-up needs, in four numbers */}
          {(() => {
            const needed = d.data.filter((r) => r.kind !== "optional" || r.status === "in_hand");
            const count = (st: DataRow["status"][]) => needed.filter((r) => st.includes(r.status)).length;
            const cells: [string, number, string][] = [
              ["in hand", count(["in_hand"]), "pill-hit"], ["open data", count(["available"]), "pill-open"],
              ["can be derived", count(["derivable"]), "pill-open"], ["no source", count(["missing", "needs_component"]), "pill-warn"],
            ];
            return (
              <div className="side-card">
                <div className="section-head"><h4>Data the set-up needs</h4>
                  <button className="link-btn" onClick={() => setTab("summary")}>details</button></div>
                <div className="data-counts">
                  {cells.map(([label, n, css]) => (
                    <span key={label} className={`data-count ${n ? css : ""}`}><strong>{n}</strong>{label}</span>
                  ))}
                </div>
              </div>
            );
          })()}
          {/* the best next step */}
          {groups.length > 0 && (() => {
            const best = groups[0].actions[0];
            const gain = best.effect.fit_after - best.effect.fit_before;
            return (
              <div className="side-card side-next">
                <div className="section-head"><h4>Best next step</h4>
                  <span className={`tag ${PRIORITY[groups[0].priority].css}`}>{PRIORITY[groups[0].priority].text}</span></div>
                <div className="side-next-msg">{best.message}</div>
                <div className="side-next-foot">
                  {!best.advice && gain > 0 && <span className="gain">fit +{gain}</span>}
                  <span className="muted">{groups.length} improvement{groups.length > 1 ? "s" : ""} in all</span>
                  {!best.advice && <button className="btn btn-primary" onClick={() => onAccept(best)}>Accept</button>}
                </div>
              </div>
            );
          })()}
        </aside>
      </div>

      {/* 4. one thing at a time */}
      <div className="tabs" role="tablist" id="improvements">
        <button role="tab" aria-selected={tab === "improve"} className={`tab${tab === "improve" ? " on" : ""}`} onClick={() => setTab("improve")}>
          Improvements <span className="tab-count">{open.length}</span>
        </button>
        {d.outputs.length > 0 && (
          <button role="tab" aria-selected={tab === "outputs"} className={`tab${tab === "outputs" ? " on" : ""}`} onClick={() => setTab("outputs")}>
            Expected outputs <span className="tab-count">{d.outputs.length}</span>
          </button>
        )}
        <button role="tab" aria-selected={tab === "summary"} className={`tab${tab === "summary" ? " on" : ""}`} onClick={() => setTab("summary")}>
          Workflow summary
        </button>
      </div>

      {tab === "improve" && (
        <>
          {groups.length === 0 && (
            <p className="muted empty-note">
              {hidden.length ? "Every suggestion was declined." : "Nothing to improve: no action found."}
            </p>
          )}
          {groups.length > 0 && (
            <p className="group-note">
              Grouped by what is missing. Each group shows its best option first; accepting one updates the diagnosis.
            </p>
          )}
          {groups.map((group) => {
            const all = expanded.includes(group.key);
            const shown = all ? group.actions : group.actions.slice(0, 1);
            const more = group.actions.length - 1;
            return (
              <div key={group.key} id={groupId(group.target)} className="action-group">
                <div className="action-group-head">
                  <span className="target-kind">{targetTitle(group.target)}</span>
                  <strong>{name(group.target)}</strong>
                  {group.target.type === "data" && group.target.use && group.target.use !== "calibration" && (
                    <span className="muted">{KIND[group.target.use]}</span>
                  )}
                  <span className={`tag ${PRIORITY[group.priority].css}`}>{PRIORITY[group.priority].text}</span>
                </div>
                {group.target.definition && (
                  <div className="muted action-group-def">
                    {group.target.type === "method" ? `used as ${group.target.definition}` : group.target.definition}
                  </div>
                )}
                {shown.map((action) => (
                  <ActionCard key={action.id} action={action} declined={false}
                              onAccept={() => onAccept(action)} onDecline={() => onDecline([action.id])}
                              onRestore={() => onRestore([action.id])} />
                ))}
                <div className="action-group-foot">
                  {more > 0 && (
                    <button className="link-btn"
                            onClick={() => setExpanded(all ? expanded.filter((k) => k !== group.key) : [...expanded, group.key])}>
                      {all ? "Show only the best option" : `Show ${more} other option${more > 1 ? "s" : ""}`}
                    </button>
                  )}
                  {group.actions.length > 1 && (
                    <button className="link-btn" onClick={() => onDecline(group.actions.map((a) => a.id))}>
                      Decline all {group.actions.length}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
          {hidden.length > 0 && (
            <div className="declined-bar">
              <span>{hidden.length} declined suggestion{hidden.length > 1 ? "s" : ""} hidden.</span>
              <button className="link-btn" onClick={() => setShowDeclined(!showDeclined)}>{showDeclined ? "Hide them" : "Show them"}</button>
              <button className="link-btn" onClick={() => onRestore(null)}>Restore all</button>
            </div>
          )}
          {showDeclined && hidden.map((action) => (
            <ActionCard key={action.id} action={action} declined onAccept={() => onAccept(action)}
                        onDecline={() => undefined} onRestore={() => onRestore([action.id])} />
          ))}
          {result.more_available > 0 && (
            <p className="meta">{result.more_available} less useful option(s) are not listed.</p>
          )}
        </>
      )}

      {tab === "outputs" && (
        <>
          <p className="group-note">
            How each expected output is obtained: the output is built from one or more variables, and each variable
            must be computed by a method of your set-up (or derived from another variable).
          </p>
          {d.outputs.map((o) => (
            <div key={o.id} className="output-card">
              <div className="action-group-head">
                <strong>{name(o)}</strong>
                {o.forms.map((f) => <span key={f.id} className="pill" title={f.definition ?? undefined}>{name(f)}</span>)}
                <span className={`tag ${o.status === "delivered" ? "tag-soft" : "tag-hard"}`}>{OUTPUT_STATUS[o.status].text}</span>
              </div>
              {o.question && <div className="opt-question">{o.question}</div>}
              {o.definition && <div className="muted output-def">{o.definition}</div>}
              <div className="colour-key">
                <span><i className="key kind-method" /> method</span>
                <span><i className="key kind-variable" /> variable it computes</span>
                <span><i className="key kind-output" /> expected output</span>
                <span className="muted">· a red box is what is missing</span>
              </div>
              <div className="trace">
                {o.trace.map((v) => {
                  // computed as such, or obtained from what the set-up computes (a derivation)
                  const ok = v.computed_by.length > 0 || !!v.derived;
                  return (
                    <div key={v.id} className="trace-row">
                      <span className={`trace-box kind-method ${ok ? "dg-ok" : "dg-bad"}`}>
                        <span className="trace-kind">method</span>
                        {v.computed_by.length > 0 ? names(v.computed_by)
                          : v.derived ? `${names(v.derived.computed_by)} (computes ${names(v.derived.from)})`
                          : "none in your set-up"}
                      </span>
                      <span className="trace-arrow">{v.computed_by.length === 0 && v.derived ? "gives, by derivation →" : "computes →"}</span>
                      <span className={`trace-box kind-variable ${ok ? "dg-ok" : "dg-bad"}`}>
                        <span className="trace-kind">variable</span>
                        {name(v)}
                      </span>
                      <span className="trace-arrow">{o.needs_grid ? "mapped →" : "gives →"}</span>
                      <span className={`trace-box kind-output ${o.status === "delivered" ? "dg-ok" : "dg-bad"}`}>
                        <span className="trace-kind">expected output</span>
                        {name(o)}
                      </span>
                      {v.computed_by.length === 0 && v.derived && (
                        <div className="trace-note">
                          {name(v)} is not computed as such: it is obtained from {names(v.derived.from)}
                          {v.derived.how ? ` (${v.derived.how})` : ""}. No other method is needed.
                        </div>
                      )}
                      {v.derivations.length > 0 && !(v.computed_by.length === 0 && v.derived) && (
                        <div className="trace-note">
                          {name(v)} can also be derived {v.derivations.map(derivationText).join("; or ")}.
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
              {o.needs_grid && (
                <div className={`trace-note ${o.drawable ? "" : "warn"}`}>
                  A map needs the variable on a grid, so it must come from a distributed or 2D/3D method:{" "}
                  {o.trace.some((v) => v.gridded_by.length)
                    ? `${names(o.trace.flatMap((v) => v.gridded_by))} can draw it.`
                    : "no method of your set-up can."}
                </div>
              )}
              {o.status !== "delivered" && (
                <button className="link-btn" onClick={() => jumpTo(`output:${o.id}`)}>See how to deliver it</button>
              )}
            </div>
          ))}
        </>
      )}

      {tab === "checks" && (
        <div className="check-list">
          {d.checks.map((check) => (
            <div key={check.id} className={`check check-${check.status}`}>
              <span className="check-mark">{check.status === "ok" ? "✓" : check.status === "fail" ? "✗" : "!"}</span>
              <div>
                <div className="check-title">{check.title}</div>
                <div className="check-message">{check.message}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "summary" && (
        <>
          <div className="section-head">
            <h4>Chain of methods</h4>
            <button className="link-btn" onClick={copySummary}>{copied ? "Copied ✓" : "Copy the summary as text"}</button>
          </div>
          <p className="group-note">
            Each method is one component of the model. A component you do not need can be left out:
            you are told first which processes, outputs and inputs are lost.
          </p>
          <div className="chain-cards">
            {d.setup.methods.map((m, index) => {
              const next = d.links.filter((l) => l.from === m.id);
              const part = result.components.find((c) => c.id === m.id);
              return (
                <div key={m.id} className={`chain-card${leaving === m.id ? " is-leaving" : ""}${autoAdded[m.id] ? " is-added" : ""}`}>
                  {autoAdded[m.id] && (
                    <div className="added-banner">
                      ✦ Improvement: added automatically so that the workflow delivers <strong>{autoAdded[m.id]}</strong>.
                      {software && m.runs_in && m.runs_in.id !== software.id
                        ? ` It runs in ${name(m.runs_in)}, another software (no method of ${name(software)} could do it).`
                        : software ? ` Same software (${name(software)}).` : ""}
                      {" "}Change it or leave it out below.
                    </div>
                  )}
                  <div className="chain-card-head">
                    <span className="chain-num">{index + 1}</span>
                    <span className="chain-icon" title={names(m.roles)}>{ROLE_ICON[m.roles[0]?.id] ?? "⚙️"}</span>
                    <div className="chain-card-title">
                      <button className={`method-open${details === m.id ? " on" : ""}`} aria-expanded={details === m.id}
                              title="Inputs, parameters, outputs and how it runs" onClick={() => setDetails(details === m.id ? null : m.id)}>
                        <strong>{name(m)}</strong> <span className="method-open-hint">{details === m.id ? "hide details" : "details"}</span>
                      </button>
                      <div className="chain-roles">
                        {m.roles.length === 0 && <span className="muted">no recorded job</span>}
                        {m.roles.map((r) => <span key={r.id} className="role-chip">{name(r)}</span>)}
                        {m.roles.length > 1 && <span className="role-chip chip-package" title="One calculation doing several jobs">package</span>}
                        {m.essential
                          ? <span className="role-chip chip-needed" title="The study cannot do without it">essential</span>
                          : <span className="role-chip chip-optional" title="Its effect can be neglected at first">optional</span>}
                      </div>
                    </div>
                    <div className="chain-card-tools">
                      {part && part.alternatives.length > 0 && (
                        <button className={`tool-btn${switching === m.id ? " on" : ""}`}
                                title="Other methods of the same software for this job"
                                onClick={() => { setSwitching(switching === m.id ? null : m.id); setLeaving(null); }}>
                          ⇄ Change method <span className="tool-count">{part.alternatives.length}</span>
                        </button>
                      )}
                      {part && (
                        <button className={`tool-btn tool-leave${leaving === m.id ? " on" : ""}`}
                                title="See what is lost without this component"
                                onClick={() => { setLeaving(leaving === m.id ? null : m.id); setSwitching(null); }}>
                          {leaving === m.id ? "Keep it" : "⊖ Leave out"}
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="chain-card-flow">
                    <span className="flow-chip">
                      Runs in {m.runs_in ? name(m.runs_in) : software ? name(software) : m.software.length ? `${names(m.software.slice(0, 4))}${m.software.length > 4 ? "…" : ""}` : "no software recorded"}
                    </span>
                    {m.module && (
                      <span className="flow-chip module-chip" title={m.module.name ?? ""}>
                        {m.module.name} · ⏱ {m.module.time_step} · ◫ {m.module.spatial_unit} · ▦ {m.module.resolution}
                      </span>
                    )}
                    {next.map((l) => {
                      const to = d.setup.methods.find((x) => x.id === l.to);
                      return (
                        <span key={l.to} className={`flow-chip flow-pass${l.optional_only ? " flow-optional" : ""}`}
                              title={l.optional_only ? "Optional exchange: the receiver also runs without it" : "Required exchange"}>
                          {l.optional_only ? "⇢" : "→"} {names(l.variables)} to <strong>{to ? name(to) : l.to}</strong>
                          {l.optional_only && " (optional)"}
                        </span>
                      );
                    })}
                  </div>
                  {details === m.id && <MethodDetails id={m.id} data={d.data} expected={d.outputs} />}
                  {part && switching === m.id && (
                    <div className="swap-box">
                      <div className="leave-title">
                        Other methods for {names(m.roles)} · the same software first
                      </div>
                      {part.alternatives.map((x) => (
                        <div key={x.id} className="swap-row">
                          <div>
                            <strong>{name(x)}</strong>{" "}
                            <span className={`pill ${x.same_software ? "pill-hit" : "pill-warn"}`}>
                              {x.same_software ? "same software" : `another software${x.software.length ? `: ${names(x.software)}` : ""}`}
                            </span>
                            {x.module && <div className="muted">⏱ {x.module.time_step} · ▦ {x.module.resolution}</div>}
                            <div className="muted">
                              Fit {part.effect.fit_before} → {x.fit_after}
                              {x.blocking_after > 0 && ` · ${x.blocking_after} blocking issue(s)`}
                              {x.outputs_lost.length > 0 && ` · no longer delivers ${x.outputs_lost.join(", ")}`}
                            </div>
                          </div>
                          <button className="btn" onClick={() => { setSwitching(null); onSwap(m, x); }}>Use it instead</button>
                        </div>
                      ))}
                    </div>
                  )}
                  {part && leaving === m.id && (
                    <>
                      <Losses part={part} />
                      <button className="btn" onClick={() => { setLeaving(null); onLeaveOut(part); }}>
                        Leave {name(m)} out
                      </button>
                    </>
                  )}
                </div>
              );
            })}
          </div>
          {d.setup.left_out.length > 0 && (
            <div className="left-out">
              <strong>Left out on purpose</strong> <span className="muted">(not proposed again)</span>
              {d.setup.left_out.map((m) => (
                <div key={m.id} className="leave-line">
                  {name(m)} <span className="muted">as {names(m.roles)}</span>{" "}
                  <button className="link-btn" onClick={() => onPutBack(m)}>Put back</button>
                </div>
              ))}
            </div>
          )}
          {d.best_template && d.best_template.slots.some((slot) => slot.mandatory && slot.filled_by.length === 0) && (
            <p className="group-note">
              Not in the chain yet:{" "}
              {d.best_template.slots.filter((slot) => slot.mandatory && slot.filled_by.length === 0).map((slot) => name(slot.role)).join(", ")}.
            </p>
          )}

          <div className="section-head"><h4>Data required and where it comes from</h4></div>
          <div className="colour-key">
            <span><i className="key nature-forcing" /> forcing</span>
            <span><i className="key nature-boundary" /> boundary condition</span>
            <span><i className="key nature-static" /> static description</span>
            <span><i className="key nature-initial" /> initial state</span>
          </div>
          <table className="data-table">
            <thead>
              <tr><th>Data</th><th>Kind</th><th>Used by</th><th>Source</th></tr>
            </thead>
            <tbody>
              {d.data.map((row) => (
                <tr key={`${row.kind}-${row.id}`}>
                  <td><i className={`key nature-${row.nature}`} /> <strong>{name(row)}</strong></td>
                  <td>
                    <span className={`nature-tag nature-${row.nature}`}>{NATURE[row.nature]}</span>
                    <div className={`use-tag use-${row.kind}`}>{KIND[row.kind]}</div>
                  </td>
                  <td>{names(row.used_by)}</td>
                  <td><Source row={row} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="meta">
            <button className="link-btn" onClick={() => onEdit(2)}>Change the data you have</button>
            <button className="link-btn" onClick={() => onEdit(0)}>Change the methods</button>
          </p>
        </>
      )}
    </div>
  );
}
