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
import DataEntry from "./components/DataEntry";
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
import SetupEntry from "./components/SetupEntry";
import type { SetupRequest } from "./setupApi";
import Wizard from "./components/Wizard";
import WorkflowSection from "./components/WorkflowSection";
import { CHALLENGE_STEPS, DATA_STEPS, SOFTWARE_STEPS } from "./steps";


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
  // the portal opens on "Start from data", or on the ontology when the address points to a term
  const [entry, setEntry] = useState<Entry | null>(() => (window.location.hash.startsWith("#/ontology") ? "ontology" : "data"));
  const ontologyTerm = useRef<string | null>(decodeURIComponent(window.location.hash.match(/^#\/ontology\/(.+)$/)?.[1] ?? "") || null);
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
  const [adjusting, setAdjusting] = useState<SetupRequest | null>(null);
  const [adjustRun, setAdjustRun] = useState(0);
  const savedScroll = useRef(0);
  const adjustingRef = useRef(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [catalogue, setCatalogue] = useState(false);       // the open data catalogue, slid in from the right

  const lastRequest = useRef(0);   // only the answer to the latest request is shown

  async function handleFinish(draft: Draft, readable: Record<string, string>) {
    const mine = ++lastRequest.current;
    const latest = () => mine === lastRequest.current;
    setAnswers(draft);
    setLabels(readable);
    setLoading(true);
    setError(null);
    try {
      if (entry === "software") {
        let ids = draft.methods ?? [];
        if (ids.length === 0) {
          // no preference: take every method of the software
          const all = await getOptions("method", draft);
          ids = all.filter((o) => o.enabled).map((o) => o.id);
        }
        const found = await Promise.all(ids.map(getMethod));
        if (latest()) setProfiles(found);
      } else if (entry === "challenge") {
        const found = await recommend(toRequest(draft));
        if (latest()) setResult(found);
      }
    } catch (e) {
      if (latest()) setError(String(e));
    } finally {
      if (latest()) setLoading(false);
    }
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
    window.history.pushState({ aio: "diagnosis" }, "");   // the browser's back button comes back here
    window.scrollTo({ top: 0 });
  }

  function closeDiagnosis() {
    adjustingRef.current = false;
    setAdjusting(null);
    // after the results are shown again, put the page where it was
    requestAnimationFrame(() => requestAnimationFrame(() => window.scrollTo({ top: savedScroll.current })));
  }

  useEffect(() => {
    // a link to the ontology (#/ontology/<term>) opens its tab, even when the portal is already open
    const onHash = () => {
      const match = window.location.hash.match(/^#\/ontology\/?(.*)$/);
      if (!match) return;
      ontologyTerm.current = match[1] ? decodeURIComponent(match[1]) : null;
      setEntry((current) => (current === "ontology" ? current : "ontology"));
    };
    window.addEventListener("hashchange", onHash);
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") setCatalogue(false); };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("hashchange", onHash);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  useEffect(() => {
    const onBack = () => {
      if (adjustingRef.current) closeDiagnosis();
    };
    window.addEventListener("popstate", onBack);
    return () => window.removeEventListener("popstate", onBack);
  }, []);

  function choose(next: Entry) {
    if (next === "ontology") {
      ontologyTerm.current = null;
      if (!window.location.hash.startsWith("#/ontology")) window.location.hash = "/ontology";
    } else if (window.location.hash.startsWith("#/ontology")) {
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    }
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
        </nav>
      </header>

      <main className="page">

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
        {entry === "software" && <SetupEntry key={`setup-${run}`} initial={handover} />}

        {entry === "data" && (
          <div hidden={!!adjusting}>
            <DataEntry key={`data-${run}`} onAdjust={adjustFromData} />
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
              <button className="btn" onClick={() => window.history.back()}>Back to {entry === "data" ? "your data" : "the recommended workflows"}</button>
              <span className="muted">Your filters, opened workflows and position are kept.</span>
            </div>
            <SetupEntry key={`adjust-${adjustRun}`} initial={adjusting} />
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