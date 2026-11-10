import { useEffect, useState } from "react";
import {
  getDatasets,
  getMethod,
  getWorkflow,
  getOptions,
  reach,
  recommend,
  type Dataset,
  type Draft,
  type MethodProfile,
  type ReachChallenge,
  type Recommendation,
  type Status,
  type Workflow,
} from "./api";
import ChallengeCard from "./components/ChallengeCard";
import CompareTable from "./components/CompareTable";
import EntryCards, { type Entry } from "./components/EntryCards";
import MethodCard from "./components/MethodCard";
import ResultCard from "./components/ResultCard";
import OpenDataLayer from "./components/OpenDataLayer";
import SearchBar from "./components/SearchBar";
import Wizard from "./components/Wizard";
import WorkflowSection from "./components/WorkflowSection";
import { CHALLENGE_STEPS, DATA_STEPS, SOFTWARE_STEPS } from "./steps";

const MAX_COMPARED = 3;

const GROUPS: { status: Status; title: string; dot: string; note?: string }[] = [
  { status: "directly_applicable", title: "Directly applicable", dot: "dot-direct" },
  { status: "needs_complementary_data", title: "Needs complementary data", dot: "dot-complement" },
  {
    status: "inputs_not_recorded",
    title: "Inputs not recorded",
    dot: "dot-unknown",
    note: "The ontology lists no inputs for these methods, so we cannot tell what data they need.",
  },
];

export default function App() {
  const [entry, setEntry] = useState<Entry | null>(null);
  const [run, setRun] = useState(0);                       // bumped to restart the wizard
  const [answers, setAnswers] = useState<Draft | null>(null);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [result, setResult] = useState<Recommendation | null>(null);
  const [profiles, setProfiles] = useState<MethodProfile[]>([]);
  const [reached, setReached] = useState<ReachChallenge[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [graph, setGraph] = useState<Workflow | null>(null);
  const [compareMode, setCompareMode] = useState(false);
  const [compared, setCompared] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFinish(draft: Draft, readable: Record<string, string>) {
    setAnswers(draft);
    setLabels(readable);
    setLoading(true);
    setError(null);
    try {
      if (entry === "data") {
        setReached(await reach(draft.available_variables ?? []));
      } else if (entry === "software") {
        let ids = draft.methods ?? [];
        if (ids.length === 0) {
          // no preference: take every method of the software
          const all = await getOptions("method", draft);
          ids = all.filter((o) => o.enabled).map((o) => o.id);
        }
        setProfiles(await Promise.all(ids.map(getMethod)));
      } else if (entry === "challenge") {
        setResult(
          await recommend({
            challenge: draft.challenge ?? "",
            processes: draft.processes ?? [],
            available_variables: draft.available_variables ?? [],
            scales: draft.scales ?? [],
            time_steps: draft.time_steps ?? [],
          })
        );
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  // Clicking an entry card (even the selected one) starts that flow from scratch.
  function choose(next: Entry) {
    setEntry(next);
    setRun((n) => n + 1);
    setAnswers(null);
    setResult(null);
    setProfiles([]);
    setReached([]);
    setGraph(null);
    setCompareMode(false);
    setCompared([]);
    setError(null);
  }

  function toggleCompare(id: string) {
    setCompared((current) =>
      current.includes(id) ? current.filter((c) => c !== id) : [...current, id]
    );
  }

  const text = (id: string) => labels[id] ?? id;
  const comparedResults = result ? result.results.filter((r) => compared.includes(r.id)) : [];
  // Data missing in the methods on screen (or only in the compared ones, if any are ticked).
  const pool = result
    ? compared.length
      ? result.results.filter((r) => compared.includes(r.id))
      : result.results.filter((r) => r.status === "needs_complementary_data")
    : [];
  const wanted = [...new Set(pool.flatMap((r) => r.inputs_missing.map((i) => i.id)))].sort();
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
  // The workflow and graph follow the compared methods, or the top 3 if none are ticked.
  const focusKey = compared.join(",");
  useEffect(() => {
    if (entry !== "challenge" || !result || !answers) {
      setGraph(null);
      return;
    }
    let cancelled = false;
    getWorkflow({
      challenge: answers.challenge ?? "",
      processes: answers.processes ?? [],
      available_variables: answers.available_variables ?? [],
      scales: answers.scales ?? [],
      time_steps: answers.time_steps ?? [],
      methods: focusKey ? focusKey.split(",") : [],
    })
      .then((g) => {
        if (!cancelled) setGraph(g);
      })
      .catch(() => {
        if (!cancelled) setGraph(null);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result, focusKey]);
  const restart = entry !== null && (
    <div className="actions">
      <button className="btn" onClick={() => choose(entry)}>
        Start again
      </button>
    </div>
  );

  return (
    <>
      <header className="header">
        <div className="header-inner">
          <div className="logo">∿</div>
          <div>
            <div className="brand-title">Hydrology Decision Support</div>
            <div className="brand-sub">Ontology-driven model &amp; open-data recommendation</div>
          </div>
          <SearchBar />
        </div>
      </header>

      <main className="page">
        <h1 className="page-title">Hydrology Decision Support System</h1>
        <p className="page-sub">
          Explore models, methods, processes and data requirements through the ontology.
        </p>

        <EntryCards selected={entry} onChoose={choose} />

        {entry !== null && answers === null && (
          <Wizard
            key={`${entry}-${run}`}
            steps={
              entry === "challenge"
                ? CHALLENGE_STEPS
                : entry === "software"
                ? SOFTWARE_STEPS
                : DATA_STEPS
            }
            onFinish={handleFinish}
          />
        )}

        {entry === "data" && answers !== null && (
          <section className="panel">
            <div className="panel-head">
              <div>
                <h2 className="panel-title">What your data allows</h2>
                <p className="panel-sub">
                  Data provided:{" "}
                  {(answers.available_variables ?? []).map(text).join(", ") || "none"}
                </p>
              </div>
            </div>
            {loading && <p className="muted">Checking every challenge…</p>}
            {error && <p className="error">{error}</p>}
            {reached.map((item) => (
              <ChallengeCard key={item.id} item={item} />
            ))}
            {restart}
          </section>
        )}

        {entry === "software" && answers !== null && (
          <section className="panel">
            <div className="panel-head">
              <div>
                <h2 className="panel-title">Methods you can run in {text(answers.software ?? "")}</h2>
                <p className="panel-sub">
                  {profiles.length} method(s). Open one to check your data against it.
                </p>
              </div>
            </div>
            {loading && <p className="muted">Loading method details…</p>}
            {error && <p className="error">{error}</p>}
            {profiles.map((p) => (
              <MethodCard key={p.id} profile={p} />
            ))}
            {restart}
          </section>
        )}

        {entry === "challenge" && answers !== null && (
          <>
          <div className="split">
          <section className="panel">
            <div className="panel-head">
              <div>
                <h2 className="panel-title">Model recommendations</h2>
                <p className="panel-sub">Models ranked according to the ontology and your requirements.</p>
              </div>
              <label className="compare-mode">
                <input
                  type="checkbox"
                  checked={compareMode}
                  onChange={(e) => {
                    setCompareMode(e.target.checked);
                    if (!e.target.checked) setCompared([]);
                  }}
                />
                Compare mode
              </label>
            </div>

            <p className="meta">
              Challenge: <strong>{text(answers.challenge ?? "")}</strong> · Data provided:{" "}
              <strong>{answers.available_variables?.length ?? 0}</strong>
              {(answers.scales?.length ?? 0) > 0 && (
                <> · Scale: <strong>{answers.scales!.map(text).join(", ")}</strong></>
              )}
              {(answers.time_steps?.length ?? 0) > 0 && (
                <> · Time step: <strong>{answers.time_steps!.map(text).join(", ")}</strong></>
              )}
            </p>

            {loading && <p className="muted">Looking for methods…</p>}
            {error && <p className="error">{error}</p>}

            {result && (
              <>
                <p className="meta">
                  Processes used: {result.urr.processes.values.map(text).join(", ")} (
                  {result.urr.processes.source === "stated"
                    ? "you chose them"
                    : "all processes of the challenge"}
                  )
                </p>
                {result.filtered_out > 0 && (
                  <p className="meta">
                    {result.filtered_out} method(s) hidden by your scale / time step filters.
                  </p>
                )}

                <CompareTable results={comparedResults} onRemove={toggleCompare} />

                {GROUPS.map((group) => {
                  const items = result.results.filter((r) => r.status === group.status);
                  if (items.length === 0) return null;
                  return (
                    <section key={group.status} className="group">
                      <h3 className="group-title">
                        <span className={`dot ${group.dot}`}></span>
                        {group.title} <span className="group-count">{items.length}</span>
                      </h3>
                      {group.note && <p className="group-note">{group.note}</p>}
                      {items.map((r) => (
                        <ResultCard
                          key={r.id}
                          result={r}
                          text={text}
                          compareMode={compareMode}
                          compared={compared.includes(r.id)}
                          canCompare={compared.length < MAX_COMPARED}
                          onToggleCompare={() => toggleCompare(r.id)}
                        />
                      ))}
                    </section>
                  );
                })}
              </>
            )}
            {restart}
          </section>

          {result && (
            <OpenDataLayer
              datasets={datasets}
              scope={compared.length ? "for the compared methods" : "for the data missing in the methods listed"}
              nothingMissing={wanted.length === 0}
            />
          )}
          </div>

          {graph && (
            <WorkflowSection
              graph={graph}
              scope={compared.length ? "from the compared methods" : "from the top 3 methods"}
            />
          )}
          </>
        )}
      </main>
    </>
  );
}