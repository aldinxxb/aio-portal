import { useEffect, useRef, useState } from "react";
import {
  getDatasets,
  getMethod,
  getChains,
  getOptions,
  recommend,
  type Dataset,
  type Draft,
  type MethodProfile,
  type Recommendation,
  type RecommendRequest,
  type Chain,
  type ChainRecommendation,
  type Licence,
} from "./api";
import DataEntry, { type DataState } from "./components/DataEntry";
import type { DataItem } from "./dataApi";
import Credits from "./components/Credits";
import EntryCards, { type Entry } from "./components/EntryCards";
import OntologyEntry from "./components/OntologyEntry";
import { EntryHero } from "./components/EntryFrame";
import FilterBar from "./components/FilterBar";
import ExpectedOutputs from "./components/ExpectedOutputs";
import MethodCard from "./components/MethodCard";
import OpenDataLayer from "./components/OpenDataLayer";
import RequirementsPanel from "./components/RequirementsPanel";
import SearchBar from "./components/SearchBar";
import SummaryGraph from "./components/SummaryGraph";
import SetupEntry, { type SetupState } from "./components/SetupEntry";
import type { SetupRequest } from "./setupApi";
import Wizard from "./components/Wizard";
import WorkflowSection from "./components/WorkflowSection";
import { CHALLENGE_STEPS, DATA_STEPS, SOFTWARE_STEPS } from "./steps";
import {
  addressOf, ago, dropDraft, fullSetupRequest, loadDraft, readAddress, saveDraft, writeAddress, type Draft as SavedDraft,
} from "./share";

// The Water Challenge results as kept in the address: the answers and how to name them.
type ChallengeState = { answers: Draft; labels: Record<string, string>; licence?: Licence; software?: string | null; focus?: string | null };


// The wizard answers of Entry 1 in the shape the backend expects (a URR).
function toRequest(draft: Draft): RecommendRequest {
  return {
    challenge: draft.challenge ?? "",
    processes: draft.processes ?? [],
    available_variables: draft.available_variables ?? [],
    scales: draft.scales ?? [],
    time_steps: draft.time_steps ?? [],
    data_time_step: draft.data_time_step,
    objective: draft.objective,
    entity: draft.entity,
    drivers: draft.drivers ?? [],
    outputs: draft.outputs ?? [],
  };
}

export default function App() {
  // The portal opens where the address says (a shared link, a reload), else on "Start from data".
  const start = useRef(readAddress());
  const [entry, setEntry] = useState<Entry | null>(start.current.entry);
  const ontologyTerm = useRef<string | null>(start.current.term);
  // the study an entry starts from: a link, a reload or a resumed draft
  const [saved, setSaved] = useState<unknown | null>(start.current.state);
  // an unfinished study of this entry, offered back when the address holds none
  const [resume, setResume] = useState<SavedDraft | null>(() =>
    start.current.state || start.current.entry === "ontology" ? null : loadDraft(start.current.entry));
  const current = useRef<unknown | null>(start.current.state);   // the entry's study, as last reported
  const diagnosisState = useRef<unknown | null>(start.current.diagnosis);   // the open diagnosis, as last reported
  const pushedDiagnosis = useRef(false);                         // opened here (back works) or from a link
  const [copied, setCopied] = useState(false);
  const [run, setRun] = useState(0);                       // bumped to restart the wizard
  const [answers, setAnswers] = useState<Draft | null>(null);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [result, setResult] = useState<Recommendation | null>(null);
  const [profiles, setProfiles] = useState<MethodProfile[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [chains, setChains] = useState<ChainRecommendation | null>(null);   // recommended workflows
  const [licence, setLicence] = useState<Licence>(null);                    // software licence filter
  const [chainSoftware, setChainSoftware] = useState<string | null>(null);  // the software the user works in
  const [handover, setHandover] = useState<SetupRequest | null>(null);      // a workflow sent to the diagnosis
  const [focus, setFocus] = useState<string | null>(null);         // the workflow the summary focuses on
  // A workflow's diagnosis opened from the results. The results stay mounted (hidden), so
  // coming back finds them as they were: filters, opened cards, focus; the scroll is restored.
  const [adjusting, setAdjusting] = useState<SetupRequest | null>(() =>
    fullSetupRequest((start.current.diagnosis as { request?: unknown } | null)?.request));
  const [adjustRun, setAdjustRun] = useState(0);
  const savedScroll = useRef(0);
  const adjustingRef = useRef(!!start.current.diagnosis);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [catalogue, setCatalogue] = useState(false);       // the open data catalogue, slid in from the right

  const lastRequest = useRef(0);   // only the answer to the latest request is shown

  async function handleFinish(draft: Draft, readable: Record<string, string>, which: Entry | null = entry) {
    const mine = ++lastRequest.current;
    const latest = () => mine === lastRequest.current;
    setAnswers(draft);
    setLabels(readable);
    setLoading(true);
    setError(null);
    try {
      if (which === "software") {
        let ids = draft.methods ?? [];
        if (ids.length === 0) {
          // no preference: take every method of the software
          const all = await getOptions("method", draft);
          ids = all.filter((o) => o.enabled).map((o) => o.id);
        }
        const found = await Promise.all(ids.map(getMethod));
        if (latest()) setProfiles(found);
      } else if (which === "challenge") {
        const found = await recommend(toRequest(draft));
        if (latest()) setResult(found);
      }
    } catch (e) {
      if (latest()) setError(String(e));
    } finally {
      if (latest()) setLoading(false);
    }
  }

  // ---- the address -------------------------------------------------------------------------
  // An entry reports its study on every change: it goes to the address (no new history step)
  // and, once there is something to keep, to the draft of that entry.
  const entryRef = useRef(entry);
  entryRef.current = entry;
  function report(which: Entry, state: unknown | null, summary: string) {
    if (which !== entryRef.current) return;
    current.current = state;
    writeAddress(addressOf(which, state, adjustingRef.current ? diagnosisState.current : null));
    if (summary) {
      saveDraft(which, state, summary);
      setResume(null);    // a new study replaces the one offered back
    }
  }
  function reportDiagnosis(state: unknown) {
    if (!adjustingRef.current) return;
    diagnosisState.current = state;
    if (entryRef.current && entryRef.current !== "ontology") writeAddress(addressOf(entryRef.current, current.current, state));
  }

  // Restore Water Challenge results from a link or a draft: the answers are asked again.
  function restoreChallenge(state: unknown) {
    const st = state as ChallengeState | null;
    if (!st?.answers?.challenge) return false;
    setLicence(st.licence ?? null);
    setChainSoftware(st.software ?? null);
    setFocus(st.focus ?? null);
    handleFinish(st.answers, st.labels ?? {}, "challenge");
    return true;
  }

  // A filter was changed or removed on the results page: same request, new answers.
  function changeFilters(draft: Draft, extraLabels: Record<string, string>) {
    setFocus(null);    // the focused workflow may no longer be in the list
    handleFinish(draft, { ...labels, ...extraLabels });
  }

  // Clicking an entry card (even the selected one) starts that flow from scratch.
  // "Check and adjust this workflow": the chain goes to the Modeling Approach diagnosis with the
  // study already described here (challenge, goal, outputs, data in hand). One engine judges both.
  function adjust(chain: Chain) {
    if (!answers) return;
    const reference = chain.kind === "reference";
    const request: SetupRequest = {
      setup: {
        software: chainSoftware,
        reference_chain: reference ? chain.id : null,
        // always the full list of methods: a later change (swap, leave out) edits this list
        methods: chain.steps.map((s) => s.method.id),
        roles: reference ? {} : Object.fromEntries(chain.steps.map((s) => [s.method.id, s.roles.map((r) => r.id)])),
      },
      context: {
        challenge: answers.challenge ?? null,
        objective: answers.objective ?? null,
        intent: null,
        scenario: null,
        outputs: answers.outputs ?? [],
        output_step: answers.time_steps?.[0] ?? null,
        entity: answers.entity ?? null,
      },
      data: (answers.available_variables ?? []).map((variable) => ({
        variable, source: "own" as const, dataset: null, step: answers.data_time_step ?? null, resolution_m: null,
      })),
    };
    openDiagnosis(request);
  }

  // "Open its diagnosis" from the Start-from-data entry: the study described there.
  function adjustFromData(chain: Chain, study: { challenge: string; objective: string | null; outputs: string[]; data: DataItem[] }) {
    const reference = chain.kind === "reference";
    openDiagnosis({
      setup: {
        software: null,
        reference_chain: reference ? chain.id : null,
        methods: chain.steps.map((s) => s.method.id),
        roles: reference ? {} : Object.fromEntries(chain.steps.map((s) => [s.method.id, s.roles.map((r) => r.id)])),
      },
      context: {
        challenge: study.challenge, objective: study.objective, intent: null, scenario: null,
        outputs: study.outputs, output_step: null, entity: null,
      },
      data: study.data.map((d) => ({
        variable: d.variable, source: d.source, dataset: d.dataset, step: d.step, resolution_m: null,
      })),
    });
  }

  function openDiagnosis(request: SetupRequest) {
    savedScroll.current = window.scrollY;
    adjustingRef.current = true;
    setAdjusting(request);
    setAdjustRun((n) => n + 1);
    diagnosisState.current = { step: request.context.objective ? 3 : 1, request };
    pushedDiagnosis.current = true;
    // a new history step: the browser's back button comes back to the results
    window.history.pushState({ aio: "diagnosis" }, "", window.location.pathname + window.location.search
      + addressOf(entryRef.current!, current.current, diagnosisState.current));
    window.scrollTo({ top: 0 });
  }

  // "Back to the results": the history step when there is one, else (a diagnosis opened from a link) directly
  function leaveDiagnosis() {
    if (pushedDiagnosis.current) { window.history.back(); return; }
    closeDiagnosis();
    writeAddress(addressOf(entryRef.current!, current.current));
  }

  function closeDiagnosis() {
    adjustingRef.current = false;
    pushedDiagnosis.current = false;
    diagnosisState.current = null;
    setAdjusting(null);
    // after the results are shown again, put the page where it was
    requestAnimationFrame(() => requestAnimationFrame(() => window.scrollTo({ top: savedScroll.current })));
  }

  // Back, forward, or a link opened while the portal is open: follow the address.
  function followAddress() {
    const found = readAddress();
    if (found.entry === "ontology") {
      // the ontology page follows its own terms; from another entry, open it on that term
      if (entryRef.current !== "ontology") { ontologyTerm.current = found.term; open("ontology", null); setResume(null); }
      return;
    }
    const same = found.entry === entryRef.current
      && addressOf(found.entry, found.state) === addressOf(found.entry, current.current);
    // another study (a link pasted in an open portal): open it, and its diagnosis if the link has one
    if (!same) open(found.entry, found.state);
    const shown = adjustingRef.current ? addressOf(found.entry, null, diagnosisState.current) : null;
    const wanted = found.diagnosis ? addressOf(found.entry, null, found.diagnosis) : null;
    if (!wanted) {
      if (adjustingRef.current) closeDiagnosis();
    } else if (wanted !== shown) {
      const request = fullSetupRequest((found.diagnosis as { request?: unknown }).request);
      if (request) {
        adjustingRef.current = true;
        diagnosisState.current = found.diagnosis;
        setAdjusting(request);
        setAdjustRun((n) => n + 1);
        writeAddress(addressOf(found.entry, current.current, found.diagnosis));
      }
    }
  }
  const follow = useRef(followAddress);
  follow.current = followAddress;

  // the challenge results of a link or a reload are asked once the page is up
  useEffect(() => {
    if (start.current.entry === "challenge" && start.current.state) restoreChallenge(start.current.state);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onHash = () => follow.current();
    window.addEventListener("hashchange", onHash);
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") setCatalogue(false); };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("hashchange", onHash);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  useEffect(() => {
    const onBack = () => follow.current();
    window.addEventListener("popstate", onBack);
    return () => window.removeEventListener("popstate", onBack);
  }, []);

  // Clicking an entry tab (even the selected one) starts that flow from scratch; an unfinished
  // study of that entry is offered back.
  function choose(next: Entry) {
    if (next === "ontology") ontologyTerm.current = null;
    open(next, null);
    setResume(next === "ontology" ? null : loadDraft(next));
  }

  function resumeDraft() {
    if (!resume || !entry) return;
    open(entry, resume.state);
    setResume(null);
  }

  function discardDraft() {
    if (entry) dropDraft(entry);
    setResume(null);
  }

  async function copyLink() {
    const link = window.location.href;
    let done = false;
    try {
      await navigator.clipboard.writeText(link);
      done = true;
    } catch {
      // no clipboard access (http page, embedded view): copy from a hidden field instead
      const field = document.createElement("textarea");
      field.value = link;
      field.setAttribute("readonly", "");
      field.style.position = "fixed";
      field.style.opacity = "0";
      document.body.appendChild(field);
      field.select();
      try { done = document.execCommand("copy"); } catch { done = false; }
      field.remove();
    }
    if (!done) { window.prompt("Copy this link:", link); return; }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  // open an entry, empty or on a study (from a link or a draft)
  function open(next: Entry, state: unknown | null) {
    current.current = state;
    if (next === "ontology") {
      if (!window.location.hash.startsWith("#/ontology")) window.location.hash = "/ontology";
    } else {
      writeAddress(addressOf(next, state));
    }
    setSaved(state);
    pushedDiagnosis.current = false;
    diagnosisState.current = null;
    setHandover(null);
    adjustingRef.current = false;
    setAdjusting(null);
    setFocus(null);
    lastRequest.current++;   // forget any answer still on its way
    setLoading(false);
    setEntry(next);
    setRun((n) => n + 1);
    setAnswers(null);
    setResult(null);
    setProfiles([]);
    setError(null);
    setLicence(null);
    setChainSoftware(null);
    if (next === "challenge" && state) restoreChallenge(state);
  }

  const text = (id: string) => labels[id] ?? id;
  // The data layer lists open datasets for what the focused workflow (else the first one) still needs.
  const shownChain = chains?.chains.find((c) => c.id === focus) ?? chains?.chains[0] ?? null;
  const wanted = shownChain
    ? [...new Set(shownChain.inputs.filter((i) => i.state !== "have").map((i) => i.id))].sort()
    : [];
  const wantedKey = wanted.join(",");

  // Ask the backend which open datasets provide that data.
  useEffect(() => {
    if (!wantedKey) {
      setDatasets([]);
      return;
    }
    let cancelled = false;
    getDatasets(wantedKey.split(","))
      .then((found) => {
        if (!cancelled) setDatasets(found);
      })
      .catch(() => {
        if (!cancelled) setDatasets([]);
      });
    return () => {
      cancelled = true;
    };
  }, [wantedKey]);
  // The recommended workflows (chains of methods) follow the answers and the licence filter.
  useEffect(() => {
    if (entry !== "challenge" || !result || !answers) {
      setChains(null);
      return;
    }
    let cancelled = false;
    getChains({ ...toRequest(answers), licence, software: chainSoftware })
      .then((found) => {
        if (!cancelled) setChains(found);
      })
      .catch(() => {
        if (!cancelled) setChains({ note: null, templates: [], chains: [] });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result, licence, chainSoftware]);
  // the Water Challenge results go to the address once answered (the wizard itself is not kept)
  useEffect(() => {
    if (entry !== "challenge") return;
    if (!answers) { if (!loading) report("challenge", null, ""); return; }
    const ids = new Set(Object.values(answers).flat().filter((x): x is string => typeof x === "string"));
    const named = Object.fromEntries(Object.entries(labels).filter(([id]) => ids.has(id)));
    report("challenge", { answers, labels: named, licence, software: chainSoftware, focus } satisfies ChallengeState,
           `${labels[answers.challenge ?? ""] ?? answers.challenge ?? ""} · results`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entry, JSON.stringify(answers), licence, chainSoftware, focus]);

  const steps =
    entry === "challenge" ? CHALLENGE_STEPS : entry === "software" ? SOFTWARE_STEPS : DATA_STEPS;
  const filters = answers !== null && (
    <FilterBar steps={steps.filter((x) => !x.skipWhen?.(answers))} answers={answers} text={text} onChange={changeFilters} />
  );
  const restart = entry !== null && (
    <div className="actions">
      <button className="btn" onClick={() => choose(entry)}>
        Start again
      </button>
    </div>
  );

  return (
    <>
      {/* one app bar: brand and search on top, the three entries as tabs below */}
      <header className="header">
        <div className="header-inner">
          <img className="logo-img" src="/aio-logo.png" alt="AIO – Agir et Innover pour l'Eau" />
          <div className="brand">
            <div className="brand-title">Hydrology Decision Support</div>
            <div className="brand-sub">Ontology-driven model &amp; open-data recommendation</div>
          </div>
          <SearchBar />
        </div>
        <nav className="header-nav" aria-label="Starting points">
          <EntryCards selected={entry} onChoose={choose} />
          <button className={`catalogue-btn${catalogue ? " on" : ""}`} aria-expanded={catalogue} onClick={() => setCatalogue(!catalogue)}
                  title="Search every catalogued dataset, variable or derived parameter">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5" /><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
            </svg>
            Open data catalogue
            {entry === "challenge" && datasets.length > 0 && <span className="catalogue-count" title="datasets for the workflow in focus">{datasets.length}</span>}
          </button>
          <button className={`share-btn${copied ? " on" : ""}`} onClick={copyLink}
                  title="Copy a link to this page as it is now: it opens the same study, for you or a colleague">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7" /><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7" />
            </svg>
            <span aria-live="polite">{copied ? "Link copied" : "Copy link"}</span>
          </button>
        </nav>
      </header>

      <main className="page">
        {resume && entry && entry !== "ontology" && !adjusting && (
          <div className="resume-bar" role="status">
            <span><strong>Continue where you left off?</strong> <span className="muted">Your last study here, {ago(resume.saved)}: {resume.summary}</span></span>
            <span className="resume-actions">
              <button className="btn btn-primary" onClick={resumeDraft}>Resume</button>
              <button className="link-btn" onClick={discardDraft}>Discard</button>
            </span>
          </div>
        )}

        {/* left: the entry · right: the open data layer. "Start from data" has its own open data
            page and a large map, so it takes the whole width. */}
        <div className="full">
        <div className="split-main">
        {entry === "software" && !adjusting && (
          <EntryHero
            kicker="Start from a modeling approach"
            title="Does your method or software fit your study?"
            lead="Describe the set-up you already use and the study it is for: the portal diagnoses it, checks its data and proposes improvements, one page at a time."
          />
        )}
        {entry === "challenge" && !adjusting && (
          <EntryHero
            kicker="Start from a water challenge"
            title="Which models and data fit your water issue?"
            lead="Answer a few questions about your challenge, goal and data: the portal ranks the workflows that fit, with the data each one still needs."
          />
        )}

        {entry === "ontology" && <OntologyEntry key={`onto-${run}`} initial={ontologyTerm.current} />}

        {/* Modeling Approach: its own flow (set-up, study, data, diagnosis and improvements) */}
        {entry === "software" && (
          <SetupEntry key={`setup-${run}`} initial={handover} saved={saved as SetupState | null}
                      onState={(state, summary) => report("software", state, summary)} />
        )}

        {entry === "data" && (
          <div hidden={!!adjusting}>
            <DataEntry key={`data-${run}`} onAdjust={adjustFromData} initial={saved as DataState | null}
                       onState={(state, summary) => report("data", state, summary)} />
          </div>
        )}

        {entry === "challenge" && answers === null && (
          <Wizard key={`${entry}-${run}`} steps={steps} onFinish={handleFinish} />
        )}

        {entry === "software" && answers !== null && (
          <section className="panel">
            <div className="panel-head">
              <div>
                <h2 className="panel-title">Methods you can run in {text(answers.software ?? "")}</h2>
                <p className="panel-sub">
                  {profiles.length} method(s). Open one to add your data, see where the rest can come
                  from, and combine it with other methods.
                </p>
              </div>
            </div>
            {filters}
            {loading && <p className="muted">Loading method details…</p>}
            {error && <p className="error">{error}</p>}
            <div className="results-scroll">
            {profiles.map((p) => (
              <MethodCard key={p.id} profile={p} software={answers.software} />
            ))}
            </div>
            {restart}
          </section>
        )}

        {/* a workflow's diagnosis, opened from the results: "back" returns to them as they were */}
        {(entry === "challenge" || entry === "data") && adjusting && (
          <>
            <div className="back-bar">
              <button className="btn" onClick={leaveDiagnosis}>Back to {entry === "data" ? "your data" : "the recommended workflows"}</button>
              <span className="muted">Your filters, opened workflows and position are kept.</span>
            </div>
            <SetupEntry key={`adjust-${adjustRun}`} initial={adjusting}
                        saved={diagnosisState.current && (diagnosisState.current as SetupState).request
                          ? { ...(diagnosisState.current as SetupState), request: adjusting } : null}
                        onState={reportDiagnosis} />
          </>
        )}

        {entry === "challenge" && answers !== null && (
          <div hidden={!!adjusting}>
          {/* the study (answers and what they require) beside the expected outputs */}
          <section className="panel study-grid">
            <div className="study-col">
              <div className="panel-head">
                <div>
                  <h2 className="panel-title">Your study</h2>
                  <p className="panel-sub">Change or remove an answer here: the workflows below follow.</p>
                </div>
              </div>
              {filters}
              {loading && <p className="muted">Looking for workflows…</p>}
              {error && <p className="error">{error}</p>}
              {result && <RequirementsPanel requirements={result.requirements} excluded={[]} text={text} />}
              {restart}
            </div>
            {result && (
              <div className="study-col">
                <ExpectedOutputs result={result} />
              </div>
            )}
          </section>

          {result && chains && (
            <SummaryGraph result={result} chains={chains.chains} focus={focus} onFocus={setFocus}
                          challenge={text(answers.challenge ?? "")} />
          )}

          {result && (
            <WorkflowSection
              chains={chains}
              licence={licence}
              onLicence={setLicence}
              software={chainSoftware}
              onSoftware={setChainSoftware}
              onAdjust={adjust}
            />
          )}
          </div>
        )}
        </div>

        </div>

      </main>
      <Credits />

      {/* the open data catalogue: always one click away, without taking room from the pages */}
      {catalogue && <div className="drawer-backdrop" onClick={() => setCatalogue(false)} />}
      <div className={`drawer${catalogue ? " open" : ""}`} aria-hidden={!catalogue} inert={!catalogue} role="dialog" aria-label="Open data catalogue">
        <button className="drawer-close" onClick={() => setCatalogue(false)} title="Close (Esc)">×</button>
        <OpenDataLayer
          datasets={entry === "challenge" ? datasets : []}
          scope={entry === "challenge" && shownChain ? `for what “${shownChain.label}” still needs` : null}
          nothingMissing={wanted.length === 0}
        />
      </div>
    </>
  );
}