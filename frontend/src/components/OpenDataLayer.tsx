import { useEffect, useRef, useState } from "react";
import {
  getDatasetSuggestions,
  searchDatasets,
  type Dataset,
  type DatasetSearch,
  type DatasetSuggestions,
  type Ref,
} from "../api";

const names = (items: Ref[]) => items.map((i) => i.label ?? i.id).join(", ");

// "1940-01-01" + ongoing -> "1940 → today"
function period(d: Dataset): string | null {
  const year = (date: string | null) => (date ? date.slice(0, 4) : null);
  const start = year(d.start);
  const end = d.ongoing ? "today" : year(d.end);
  if (start && end) return `${start} → ${end}`;
  if (start) return `since ${start}`;
  if (end) return d.ongoing ? "still updated" : `until ${end}`;
  return null;
}

function DatasetCard({ d }: { d: Dataset }) {
  const when = [period(d), d.temporal_nature].filter(Boolean).join(" · ");
  return (
    <article className="data-item">
      <div className="data-head">
        <h3 className="data-title">{d.label ?? d.id}</h3>
        {d.url && /^https?:\/\//.test(d.url) && (
          <a className="data-link" href={d.url} target="_blank" rel="noreferrer" title="Open the dataset page">
            ↗
          </a>
        )}
      </div>
      {d.publishers.length > 0 && <div className="data-meta">{names(d.publishers)}</div>}
      <dl className="data-facts">
        <dt>Where</dt>
        <dd>{names(d.coverage) || "not recorded"}</dd>
        <dt>When</dt>
        <dd>{when || "not recorded"}</dd>
      </dl>
      {d.matched_by === "dataset" && (
        <div className="data-count">All {d.provides.length} variable(s) of this dataset</div>
      )}
      <ul className={`data-vars${d.provides.length > 6 ? " data-vars-long" : ""}`}>
        {d.provides.map((v) => (
          <li key={v.id}>
            <span className="pill">✓ {v.label ?? v.id}</span>
            <span className="data-res">
              {[
                v.time_steps.length ? `every ${v.time_steps.join(" / ")}` : null,
                v.grids.length ? `grid ${v.grids.join(" / ")}` : null,
              ]
                .filter(Boolean)
                .join(" · ") || "resolution not recorded"}
            </span>
          </li>
        ))}
      </ul>
    </article>
  );
}

type Props = {
  datasets: Dataset[];        // datasets for the data missing in the recommended methods
  scope: string | null;       // what that list is based on (null = no recommendation yet)
  nothingMissing: boolean;    // true when no method lacks any data
};

// Always on screen. Two uses: a free search by variable name or by dataset name, and
// (when a recommendation is shown and the search box is empty) the datasets for the
// missing data. A dataset found by its own name lists every variable it contains.
export default function OpenDataLayer({ datasets, scope, nothingMissing }: Props) {
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<DatasetSearch | null>(null);
  const [suggestions, setSuggestions] = useState<DatasetSuggestions>({ variables: [], datasets: [], derived: [] });
  const [error, setError] = useState<string | null>(null);

  // The variable names and dataset names proposed while typing.
  useEffect(() => {
    getDatasetSuggestions()
      .then(setSuggestions)
      .catch(() => setSuggestions({ variables: [], datasets: [], derived: [] }));
  }, []);

  // Search a little after the user stops typing.
  const wanted = query.trim();
  const latest = useRef("");   // the text of the last search sent: older answers are ignored
  useEffect(() => {
    latest.current = wanted;
    if (wanted.length < 2) return;
    const timer = setTimeout(() => {
      searchDatasets(wanted)
        .then((result) => {
          if (latest.current === wanted) {
            setFound(result);
            setError(null);
          }
        })
        .catch((e) => {
          if (latest.current === wanted) setError(String(e));
        });
    }, 250);
    return () => clearTimeout(timer);
  }, [wanted]);

  const searching = wanted.length >= 2;
  const shown = searching ? found?.datasets ?? [] : datasets;
  const byName = (found?.datasets ?? []).filter((d) => d.matched_by === "dataset").length;
  const derived = searching ? found?.derived ?? [] : [];

  return (
    <aside className="panel data-layer">
      <div className="panel-head">
        <div>
          <h2 className="panel-title">Open data catalogue</h2>
          <p className="panel-sub">Catalog only, no data storage</p>
        </div>
      </div>

      <div className="data-search">
        <input
          type="text"
          spellCheck={false}
          list="dataset-variables"
          placeholder="Variable, parameter or dataset, e.g. curve number, ERA5"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search datasets by variable, derived parameter or dataset name"
        />
        <datalist id="dataset-variables">
          {suggestions.variables.map((v) => (
            <option key={`v-${v.id}`} value={v.label ?? v.id}>
              variable · {v.count} dataset(s)
            </option>
          ))}
          {suggestions.derived
            .filter((v) => !suggestions.variables.some((x) => x.id === v.id))
            .map((v) => (
              <option key={`p-${v.id}`} value={v.label ?? v.id}>
                parameter · can be derived
              </option>
            ))}
          {suggestions.datasets.map((d) => (
            <option key={`d-${d.id}`} value={d.label ?? d.id}>
              dataset · {d.count} variable(s)
            </option>
          ))}
        </datalist>
        {query && (
          <button className="btn data-clear" onClick={() => setQuery("")}>
            Clear
          </button>
        )}
      </div>

      {searching && error && <p className="error">{error}</p>}

      {searching && found && (
        <p className="data-status">
          {found.datasets.length} dataset(s) found
          {byName > 0 && <> · {byName} by name (all their variables are listed)</>}
          {found.variables.length > 0 && <> · containing {names(found.variables)}</>}
          {derived.length > 0 && <> · {derived.length} can be derived</>}
        </p>
      )}
      {!searching && scope && <p className="data-status">Datasets {scope}</p>}
      {!searching && shown.length === 0 && (
        <p className="muted">
          {!scope
            ? "Type a variable name to list every dataset that contains it, a parameter (curve number, time of concentration…) to see how it is derived, or a dataset name to see all its variables."
            : nothingMissing
            ? "No missing data: nothing to look for. You can still search a variable above."
            : "No catalogued dataset provides the missing data."}
        </p>
      )}
      {searching && found && shown.length === 0 && derived.length === 0 && (
        <p className="muted">No catalogued dataset, variable or derived parameter has that name.</p>
      )}

      {derived.length > 0 && (
        <>
          <div className="data-section">How to derive it</div>
          <div className="derived-list">
            {derived.map((v) => (
              <div key={v.id} className="derived-item">
                <div className="derived-title">{v.label ?? v.id}</div>
                <div className="muted">
                  {v.datasets > 0
                    ? `Provided directly by ${v.datasets} dataset${v.datasets > 1 ? "s" : ""} (below), or derived:`
                    : "No dataset provides it directly. It is derived:"}
                </div>
                {v.derivations.map((way, i) => (
                  <div key={i} className="derived-way">
                    from{" "}
                    {way.from.map((input, j) => (
                      <span key={input.id}>
                        {j > 0 && " + "}
                        <button className="derived-input" title="Search the datasets providing it"
                                onClick={() => setQuery(input.label ?? input.id)}>
                          {input.label ?? input.id}
                        </button>
                        <span className="muted"> ({input.datasets ? `${input.datasets} dataset${input.datasets > 1 ? "s" : ""}` : "no open dataset"})</span>
                      </span>
                    ))}
                    {way.how && <div className="how">Technique: {way.how}</div>}
                  </div>
                ))}
              </div>
            ))}
          </div>
          {shown.length > 0 && <div className="data-section">Datasets</div>}
        </>
      )}

      <div className="data-list">
        {shown.map((d) => (
          <DatasetCard key={d.id} d={d} />
        ))}
      </div>
    </aside>
  );
}
