import { useEffect, useState } from "react";
import { fullSetupRequest } from "../share";
import { EntryHero, PageNav, PageSteps, type Hero } from "./EntryFrame";
import type { Ref } from "../api";
import {
  applyPatch,
  EMPTY_REQUEST,
  improveSetup,
  setupOptions,
  type Action,
  type Context,
  type DataRow,
  type Improvement,
  type Nature,
  type RoleGroup,
  type SetupOption,
  type SetupRequest,
} from "../setupApi";
import { KIND, NATURE, name, names, STATUS } from "../setupLabels";
import SetupDiagnosis from "./SetupDiagnosis";

const STEPS = [
  { title: "Your set-up", sub: "methods or a standard workflow" },
  { title: "Your study", sub: "challenge, objective, outputs" },
  { title: "Your data", sub: "what you already have" },
  { title: "Diagnosis", sub: "fit and improvements" },
];
const MORE: { field: "output_step" | "intent" | "scenario" | "entity"; label: string }[] = [
  { field: "output_step", label: "Time step of the results" },
  { field: "intent", label: "Decision intent" },
  { field: "scenario", label: "Scenario" },
  { field: "entity", label: "Water entity" },
];

type OptionList = { options: SetupOption[] };

// One list of options as buttons. An option that needs a change or a combination can
// still be picked (its reason is shown); only "unavailable" ones are greyed out.
function Choices({ options, value, onPick, empty }: {
  options: SetupOption[];
  value: string | null | string[];       // a list: several options can be picked
  onPick: (id: string | null) => void;   // a list: the option that was switched on or off
  empty?: string;
}) {
  const many = Array.isArray(value);
  const isPicked = (id: string) => (many ? value.includes(id) : value === id);
  if (options.length === 0) return <p className="muted">{empty ?? "Loading…"}</p>;
  return (
    <div className="options">
      {options.map((o) => (
        <div key={o.id} className="opt-wrap">
          <button
            className={`opt${isPicked(o.id) ? " selected" : ""}${o.suggested ? " opt-direct" : ""}`}
            disabled={o.status === "unavailable"}
            aria-pressed={isPicked(o.id)}
            onClick={() => onPick(!many && isPicked(o.id) ? null : o.id)}
          >
            {many && <span className="opt-check">{isPicked(o.id) ? "✓" : "+"}</span>}
            <span>{name(o)}</span>
            {o.status !== "ok" && o.status !== "unavailable" && <span className="opt-star">!</span>}
          </button>
          {o.question && <div className="opt-question">{o.question}</div>}
          {o.variables && o.variables.length > 0 && (
            <div className="opt-related">Variables: {names(o.variables)}</div>
          )}
          {o.reason && <div className="opt-reason">{o.reason}</div>}
        </div>
      ))}
    </div>
  );
}

// The study as kept in the address and in the draft.
export type SetupState = { step: number; request: SetupRequest; declined?: string[]; tried?: string[] };

// initial: a set-up handed over by the Water Challenge entry ("check and adjust this workflow")
// saved: a study from a link or a draft, where it was left
export default function SetupEntry({ initial, saved, onState, hero }: {
  initial?: SetupRequest | null; saved?: SetupState | null; onState?: (state: SetupState | null, summary: string) => void;
  hero?: Hero;   // the entry's banner (full on the first page, then one line); none inside a results page
}) {
  // with a challenge and an objective the diagnosis can start at once; else the study is asked first
  // a link drops empty values to stay short: the set-up is put back in its full shape
  const restored = saved ? fullSetupRequest(saved.request) : null;
  const [step, setStep] = useState(restored ? Math.min(3, Math.max(0, saved!.step ?? 0)) : initial ? (initial.context.objective ? 3 : 1) : 0);
  const [request, setRequest] = useState<SetupRequest>(restored ?? initial ?? EMPTY_REQUEST);
  const [software, setSoftware] = useState<SetupOption[]>([]);
  const [chains, setChains] = useState<SetupOption[]>([]);
  const [groups, setGroups] = useState<RoleGroup[]>([]);
  const [lists, setLists] = useState<Record<string, SetupOption[]>>({});
  const [rows, setRows] = useState<DataRow[]>([]);
  const [timeSteps, setTimeSteps] = useState<Ref[]>([]);
  const [result, setResult] = useState<Improvement | null>(null);
  const [accepted, setAccepted] = useState<string[]>([]);   // messages of the accepted actions
  const [history, setHistory] = useState<SetupRequest[]>([]); // the request before each accepted action (undo)
  const [declined, setDeclined] = useState<string[]>(saved?.declined ?? []);   // ids of the suggestions the user declined
  // An expected output the workflow does not deliver is completed AT ONCE with the best
  // matching method (same software first); the user can change it or leave it out.
  const [autoAdded, setAutoAdded] = useState<Record<string, string>>({});   // method -> output
  const [autoTried, setAutoTried] = useState<string[]>(saved?.tried ?? []);  // outputs already completed once
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // step 1 is short: one way of describing the set-up at a time, one job open at a time
  const [mode, setMode] = useState<"methods" | "workflow">("methods");
  const [openRole, setOpenRole] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [openChallenge, setOpenChallenge] = useState<string | null>(null);

  const { setup, context } = request;
  const setupKey = JSON.stringify(setup);
  const contextKey = JSON.stringify(context);

  const guard = (work: Promise<unknown>) => work.catch((e) => setError(String(e)));

  // every change goes to the address (and the draft): a reload or a shared link finds it again
  useEffect(() => {
    if (!onState) return;
    const empty = step === 0 && !request.setup.software && !request.setup.methods.length && !request.setup.reference_chain
      && !request.context.challenge && !request.data.length;
    if (empty) { onState(null, ""); return; }
    // names, from the lists this page has loaded (an id until they arrive)
    const nameOf = (id: string) => {
      const listed = [...chains, ...software, ...(lists.challenge ?? []), ...chains.flatMap((c) => c.challenges ?? [])].find((o) => o.id === id);
      return listed ? name(listed) : labelOf(id);
    };
    const methods = request.setup.methods.map(nameOf);
    const parts = [
      request.setup.reference_chain ? nameOf(request.setup.reference_chain) : methods.length ? `${methods.slice(0, 2).join(", ")}${methods.length > 2 ? ` +${methods.length - 2}` : ""}` : request.setup.software ? nameOf(request.setup.software) : "",
      request.context.challenge ? nameOf(request.context.challenge) : "",
      request.data.length ? `${request.data.length} data` : "",
    ].filter(Boolean);
    onState({ step, request, declined, tried: autoTried }, parts.join(" · "));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, JSON.stringify(request), declined.join(), autoTried.join(), groups.length, chains.length, software.length, lists.challenge?.length]);

  // step 1: software, standard workflows, and the methods grouped by the job they do
  useEffect(() => {
    guard(setupOptions<OptionList>("software", EMPTY_REQUEST).then((r) => setSoftware(r.options)));
  }, []);
  useEffect(() => {
    guard(setupOptions<{ groups: RoleGroup[] }>("methods", request).then((r) => setGroups(r.groups)));
    guard(setupOptions<OptionList>("reference_chain", request).then((r) => setChains(r.options)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setup.software]);

  // step 2: what the set-up can reach (statuses depend on the set-up and on the challenge)
  useEffect(() => {
    if (step !== 1) return;
    for (const list of ["challenge", "objective", "intent", "scenario", "entity", "output_step"]) {
      guard(setupOptions<OptionList>(list, request).then((r) => setLists((old) => ({ ...old, [list]: r.options }))));
    }
    if (context.challenge) {
      guard(setupOptions<OptionList>("output", request).then((r) => setLists((old) => ({ ...old, output: r.options }))));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, setupKey, context.challenge]);

  // step 3: the data checklist
  useEffect(() => {
    if (step !== 2) return;
    guard(
      setupOptions<{ options: DataRow[]; time_steps: Ref[] }>("data", { ...request, data: [] }).then((r) => {
        setRows(r.options);
        setTimeSteps(r.time_steps);
      })
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, setupKey, contextKey]);

  // step 4: diagnosis and actions, again after every accepted action
  useEffect(() => {
    if (step !== 3) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    improveSetup(request)
      .then((found) => {
        if (!cancelled) setResult(found);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, JSON.stringify(request)]);

  // ---- editing the request ---------------------------------------------------------
  function pickSoftware(id: string | null) {
    setRequest({ ...request, setup: { software: id, methods: [], roles: {}, reference_chain: null } });
  }

  // One method per job: picking a method for a role frees that role from any other method.
  function toggleMethod(method: string, role: string) {
    const roles: Record<string, string[]> = {};
    const had = setup.roles[method]?.includes(role) ?? false;
    for (const [m, own] of Object.entries(setup.roles)) {
      const kept = own.filter((r) => r !== role);
      if (kept.length) roles[m] = kept;
    }
    if (!had) roles[method] = [...(roles[method] ?? []), role];
    setRequest({ ...request, setup: { ...setup, roles, methods: Object.keys(roles), reference_chain: null } });
  }

  // A workflow is picked under a water challenge: that challenge becomes the one of the study
  // (it can still be changed at the next step).
  function pickChain(id: string | null, challenge?: string) {
    const chain = chains.find((c) => c.id === id);
    const changed = !!chain && !!challenge && challenge !== context.challenge;
    setRequest({
      ...request,
      setup: { ...setup, reference_chain: id, roles: {}, methods: chain ? (chain.methods ?? []).map((m) => m.id) : [] },
      context: changed ? { ...context, challenge: challenge!, outputs: [] } : context,
    });
  }

  const setContext = (change: Partial<Context>) => setRequest({ ...request, context: { ...context, ...change } });

  function toggleOutput(id: string | null) {
    if (!id) return;
    const outputs = context.outputs.includes(id) ? context.outputs.filter((o) => o !== id) : [...context.outputs, id];
    setContext({ outputs });
  }

  function toggleData(row: DataRow) {
    const has = request.data.some((d) => d.variable === row.id);
    const data = has
      ? request.data.filter((d) => d.variable !== row.id)
      : [...request.data, { variable: row.id, source: "own" as const, dataset: null, step: null, resolution_m: null }];
    setRequest({ ...request, data });
  }

  function setDataStep(variable: string, value: string) {
    setRequest({
      ...request,
      data: request.data.map((d) => (d.variable === variable ? { ...d, step: value || null } : d)),
    });
  }

  function accept(action: Action) {
    setAccepted([...accepted, action.message]);
    setHistory([...history, request]);
    setRequest(applyPatch(request, action.patch));
  }

  // Leaving a component out, or putting it back, is a change like any other: it can be undone.
  useEffect(() => {
    if (!result || loading) return;
    for (const issue of result.diagnosis.issues) {
      if (issue.code !== "OUTPUT_NEEDS_COMBINATION" || !issue.subject || autoTried.includes(issue.subject)) continue;
      const best = result.actions.find((a) => a.kind === "extend_output" && a.target.id === issue.subject);
      setAutoTried([...autoTried, issue.subject]);
      if (!best) continue;
      const added = (best.patch["setup.methods+"] as string[] | undefined) ?? [];
      const output = result.diagnosis.outputs.find((o) => o.id === issue.subject);
      const label = output?.label ?? issue.subject;
      setAutoAdded({ ...autoAdded, ...Object.fromEntries(added.map((m) => [m, label])) });
      change(`Added automatically to deliver ${label}: ${best.message.replace(/ Possible combination.*$/, "")}`, best.patch);
      return;                               // one at a time: the next diagnosis decides the rest
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result, loading]);

  function change(message: string, patch: Record<string, unknown>) {
    setAccepted([...accepted, message]);
    setHistory([...history, request]);
    setRequest(applyPatch(request, patch));
  }

  function undo() {
    if (history.length === 0) return;
    setRequest(history[history.length - 1]);
    setHistory(history.slice(0, -1));
    setAccepted(accepted.slice(0, -1));
  }

  function restart() {
    setRequest(EMPTY_REQUEST);
    setAccepted([]);
    setHistory([]);
    setDeclined([]);
    setResult(null);
    setStep(0);
  }

  // a step can be opened from the stepper once what comes before it is filled in
  const reachable = (i: number) =>
    i === 0 || (setup.methods.length > 0 && (i === 1 || (!!context.challenge && !!context.objective)));

  const canNext = step === 0 ? setup.methods.length > 0 : step === 1 ? !!context.challenge && !!context.objective : true;
  const labelOf = (id: string) => {
    for (const group of groups) {
      const found = group.options.find((o) => o.id === id);
      if (found) return name(found);
    }
    return id;
  };


  // step 1: the job each chosen method does, and the jobs matching the search box
  const pickedFor = (role: string) => Object.keys(setup.roles).find((m) => setup.roles[m].includes(role));
  const words = search.trim().toLowerCase();
  const shownGroups = !words
    ? groups
    : groups
        .map((g) => ({
          ...g,
          options: name(g.role).toLowerCase().includes(words)
            ? g.options
            : g.options.filter((o) => name(o).toLowerCase().includes(words)),
        }))
        .filter((g) => g.options.length > 0);
  // standard workflows under each water challenge they serve (a workflow may serve several)
  const byChallenge = new Map<string, { challenge: Ref; chains: SetupOption[] }>();
  for (const chain of chains) {
    for (const challenge of chain.challenges ?? []) {
      if (!byChallenge.has(challenge.id)) byChallenge.set(challenge.id, { challenge, chains: [] });
      byChallenge.get(challenge.id)!.chains.push(chain);
    }
  }
  // with a software chosen, only the workflows that use it are listed; without, all of them
  const challengeGroups = [...byChallenge.values()]
    .map((group) => ({ ...group, chains: group.chains.filter((c) => !setup.software || c.same_software) }))
    .filter((group) => group.chains.length > 0)
    .sort((x, y) => name(x.challenge).localeCompare(name(y.challenge)));
  const softwareName = software.find((s) => s.id === setup.software);
  const shownChallenge = openChallenge ?? context.challenge;
  const chosenChain = chains.find((c) => c.id === setup.reference_chain);

  // the set-up and study so far, in one line for the bottom bar
  const chosen = chosenChain ? name(chosenChain) : setup.methods.length
    ? `${setup.methods.slice(0, 2).map(labelOf).join(", ")}${setup.methods.length > 2 ? ` +${setup.methods.length - 2}` : ""}`
    : softwareName ? name(softwareName) : "";
  const findName = (list: string, id: string | null) => {
    if (!id) return "";
    const found = (lists[list] ?? []).find((o) => o.id === id);
    return found ? name(found) : "";
  };
  const navSummary = [chosen, findName("challenge", context.challenge), findName("objective", context.objective),
                      step >= 2 && request.data.length ? `${request.data.length} data in hand` : ""].filter(Boolean).join(" · ");
  const why = step === 0 ? "choose at least one method or a standard workflow" : step === 1 ? "choose a challenge and an objective" : undefined;

  return (
    <>
    {hero && <EntryHero {...hero} compact={step > 0} />}
    <section className="panel">
      <PageSteps steps={STEPS} current={step} reachable={reachable} onGo={setStep} />
      {error && <p className="error">{error}</p>}

      {step === 0 && (
        <>
          <h2 className="question">What do you already use?</h2>
          <div className="setup-bar">
            <label className="setup-software">
              <span>Software <span className="muted">(optional)</span></span>
              <select className="select" value={setup.software ?? ""} onChange={(e) => pickSoftware(e.target.value || null)}>
                <option value="">any software</option>
                {software.map((o) => (
                  <option key={o.id} value={o.id}>
                    {name(o)}{o.count ? ` (${o.count} methods)` : ""}
                  </option>
                ))}
              </select>
            </label>
            <div className="seg" role="tablist">
              <button role="tab" aria-selected={mode === "methods"} className={`seg-btn${mode === "methods" ? " on" : ""}`}
                      onClick={() => setMode("methods")}>
                Pick my methods
              </button>
              <button role="tab" aria-selected={mode === "workflow"} className={`seg-btn${mode === "workflow" ? " on" : ""}`}
                      onClick={() => setMode("workflow")}>
                Start from a standard workflow
              </button>
            </div>
          </div>

          <div className="setup-summary">
            <span className="muted">Your set-up:</span>
            {chosenChain && <span className="pill pill-open">{name(chosenChain)}</span>}
            {setup.methods.length === 0 && !chosenChain && (
              <span className="muted">
                nothing chosen yet. {mode === "workflow"
                  ? "Pick the standard workflow closest to yours below."
                  : "Open a job below (e.g. runoff transform) and tick the method you use for it, or pick your software first."}
              </span>
            )}
            {setup.methods.map((m) => (
              <span key={m} className="pill pill-hit">{labelOf(m)}</span>
            ))}
            {setup.methods.length > 0 && (
              <button className="link-btn" onClick={() => pickSoftware(setup.software)}>clear</button>
            )}
          </div>

          {mode === "workflow" && (
            <>
              <p className="group-note">
                A standard workflow is a usual combination of methods. Open the water challenge you work on and
                pick the closest to yours.{" "}
                {softwareName
                  ? `Only the workflows that use ${name(softwareName)} are listed: choose “any software” above to see them all.`
                  : "All the workflows are listed: choose a software above to see only its own."}
              </p>
              {chains.length > 0 && challengeGroups.length === 0 && softwareName && (
                <p className="muted">No standard workflow uses {name(softwareName)} yet. Pick your methods instead, or choose another software.</p>
              )}
              {chains.length === 0 && <p className="muted">Loading…</p>}
              <div className="role-list one-column">
                {challengeGroups.map((group) => {
                  const open = shownChallenge === group.challenge.id;
                  const picked = group.chains.find((c) => c.id === setup.reference_chain);
                  return (
                    <div key={group.challenge.id} className={`role-row${open ? " open" : ""}`}>
                      <button className="role-head" aria-expanded={open}
                              onClick={() => setOpenChallenge(open ? "" : group.challenge.id)}>
                        <span className="role-caret">{open ? "▾" : "▸"}</span>
                        <span className="role-name">{name(group.challenge)}</span>
                        {picked && !open ? (
                          <span className="pill pill-hit">{name(picked)}</span>
                        ) : (
                          <span className="muted role-count">{group.chains.length} workflow{group.chains.length > 1 ? "s" : ""}</span>
                        )}
                      </button>
                      {open && (
                        <div className="role-body chain-list">
                          {group.chains.map((chain) => {
                            const selected = setup.reference_chain === chain.id;
                            return (
                              <button key={chain.id} className={`chain-row${selected ? " selected" : ""}`}
                                      onClick={() => pickChain(selected ? null : chain.id, group.challenge.id)}>
                                <span className="chain-name">
                                  {name(chain)}
                                  {chain.same_software && <span className="pill pill-hit chain-tag">your software</span>}
                                </span>
                                <span className="chain-methods">{(chain.methods ?? []).map(name).join(" → ")}</span>
                                {(chain.optional_methods ?? []).length > 0 && (
                                  <span className="chain-methods muted">Optional, proposed later: {(chain.optional_methods ?? []).map(name).join(", ")}</span>
                                )}
                                {chain.delivers && chain.delivers.length > 0 && (
                                  <span className="chain-methods">Delivers: {names(chain.delivers)}</span>
                                )}
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {mode === "methods" && (
            <>
              <div className="setup-find">
                <input type="search" placeholder="Find a method or a job…" value={search}
                       onChange={(e) => setSearch(e.target.value)} />
                <span className="muted">One method per job. Open a job to choose.</span>
              </div>
              {groups.length === 0 && <p className="muted">Loading…</p>}
              {groups.length > 0 && shownGroups.length === 0 && <p className="muted">No method matches “{search}”.</p>}
              <div className="role-list">
                {shownGroups.map((group) => {
                  const picked = pickedFor(group.role.id);
                  const open = !!words || openRole === group.role.id;
                  return (
                    <div key={group.role.id} className={`role-row${open ? " open" : ""}`}>
                      <button className="role-head" aria-expanded={open}
                              onClick={() => setOpenRole(openRole === group.role.id ? null : group.role.id)}>
                        <span className="role-caret">{open ? "▾" : "▸"}</span>
                        <span className="role-name">{name(group.role)}</span>
                        {picked ? (
                          <span className="pill pill-hit">{labelOf(picked)}</span>
                        ) : (
                          <span className="muted role-count">{group.options.length} method{group.options.length > 1 ? "s" : ""}</span>
                        )}
                      </button>
                      {open && (
                        <div className="role-body">
                          {group.definition && <div className="muted role-def">{group.definition}</div>}
                          <div className="options">
                            {group.options.map((o) => {
                              const flow = [
                                o.receives?.length ? `receives ${names(o.receives)}` : null,
                                o.delivers?.length ? `gives ${names(o.delivers)}` : null,
                              ].filter(Boolean);
                              return (
                                <div key={o.id} className="opt-wrap">
                                  <button
                                    className={`opt${picked === o.id ? " selected" : ""}`}
                                    onClick={() => toggleMethod(o.id, group.role.id)}
                                    title={flow.join(" · ")}
                                  >
                                    {name(o)}
                                  </button>
                                  {o.also && o.also.length > 0 && (
                                    <div className="opt-related">can also be {names(o.also)}</div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </>
      )}

      {step === 1 && (
        <>
          <h2 className="question">What is the study for?</h2>
          <p className="group-note">
            A set-up is always judged for a study. Challenge and objective are required. “!” means your
            set-up needs a change or another method for that choice.
          </p>
          <h4 className="sub-title">Water challenge (required)</h4>
          <Choices options={lists.challenge ?? []} value={context.challenge}
                   onPick={(id) => setContext({ challenge: id, outputs: [] })} />
          <h4 className="sub-title">Study objective (required)</h4>
          <Choices options={lists.objective ?? []} value={context.objective} onPick={(id) => setContext({ objective: id })} />
          <h4 className="sub-title">
            Expected outputs (optional) <span className="muted">· pick as many as you need; each one answers a question</span>
          </h4>
          <Choices options={context.challenge ? lists.output ?? [] : []} value={context.outputs}
                   onPick={toggleOutput} empty={context.challenge ? "Loading…" : "Choose a challenge first."} />
          <h4 className="sub-title">More about the study (optional)</h4>
          <div className="selects">
            {MORE.map(({ field, label }) => (
              <label key={field}>
                {label}
                <select className="select" value={context[field] ?? ""}
                        onChange={(e) => setContext({ [field]: e.target.value || null })}>
                  <option value="">no preference</option>
                  {(lists[field] ?? []).map((o) => (
                    <option key={o.id} value={o.id}>{name(o)}</option>
                  ))}
                </select>
              </label>
            ))}
          </div>
        </>
      )}

      {step === 2 && (
        <>
          <h2 className="question">Which of these data do you already have?</h2>
          <p className="group-note">
            What the set-up needs from outside. Forcing comes from outside the water system (rain,
            temperature); a boundary condition is a flow or level entering the model at its limits;
            a static description is fixed (terrain, soil, channel).
          </p>
          {rows.length === 0 && <p className="muted">Loading the checklist…</p>}
          {(["forcing", "boundary", "static", "initial"] as Nature[]).map((nature) => {
            const items = rows.filter((r) => r.nature === nature);
            if (items.length === 0) return null;
            return (
              <div key={nature}>
                <h4 className="sub-title">{NATURE[nature]} ({items.length})</h4>
                {items.map((row) => {
                  const item = request.data.find((x) => x.variable === row.id);
                  return (
                    <div key={`${row.kind}-${row.id}`} className="line data-row">
                      <label className="tick-inline">
                        <input type="checkbox" checked={!!item} disabled={row.kind === "initial"}
                               onChange={() => toggleData(row)} />{" "}
                        <strong>{name(row)}</strong>
                      </label>
                      <span className="muted"> {KIND[row.kind]} · for {names(row.used_by)}</span>
                      {item && row.time_varying && (
                        <select className="select" value={item.step ?? ""}
                                onChange={(e) => setDataStep(row.id, e.target.value)}>
                          <option value="">time step?</option>
                          {timeSteps.map((s) => (
                            <option key={s.id} value={s.id}>{name(s)}</option>
                          ))}
                        </select>
                      )}
                      {!item && (
                        <span className={`pill ${STATUS[row.status].css}`}>{STATUS[row.status].text}</span>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </>
      )}

      {step === 3 && (
        <>
          {loading && !result && <p className="muted">Diagnosing your set-up…</p>}
          {result && (
            <SetupDiagnosis
              result={result}
              loading={loading}
              accepted={accepted}
              declined={declined}
              onAccept={accept}
              onUndo={undo}
              onDecline={(ids) => setDeclined([...declined, ...ids.filter((id) => !declined.includes(id))])}
              onRestore={(ids) => setDeclined(ids ? declined.filter((id) => !ids.includes(id)) : [])}
              onEdit={setStep}
              autoAdded={Object.fromEntries(Object.entries(autoAdded).filter(([m]) => request.setup.methods.includes(m)))}
              onLeaveOut={(component) =>
                change(`Left out: ${component.label ?? component.id}`, component.patch)}
              onSwap={(method, by) =>
                change(`Changed ${method.label ?? method.id} to ${by.label ?? by.id}`, by.patch)}
              onPutBack={(method) =>
                change(`Put back: ${method.label ?? method.id}`, {
                  "setup.methods+": [method.id],
                  "setup.roles+": { [method.id]: method.roles.map((r) => r.id) },
                  "setup.left_out-": [method.id],
                })}
            />
          )}
        </>
      )}

      <PageNav
        onBack={step > 0 ? () => setStep(step - 1) : undefined}
        summary={navSummary}
        onNext={step < 3 ? () => setStep(step + 1) : restart}
        nextLabel={step === 0 ? "Next: your study" : step === 1 ? "Next: your data" : step === 2 ? "Diagnose" : "Start again"}
        nextDisabled={step < 3 && !canNext}
        note={step < 3 && !canNext ? why : undefined}
        quiet={step === 3}
      />
    </section>
    </>
  );
}
