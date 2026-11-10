import type { Dataset, Ref } from "../api";

const names = (items: Ref[]) => items.map((i) => i.label ?? i.id).join(", ");

type Props = {
  datasets: Dataset[];
  scope: string;              // short text saying what the list is based on
  nothingMissing: boolean;    // true when no method lacks any data
};

export default function OpenDataLayer({ datasets, scope, nothingMissing }: Props) {
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2 className="panel-title">Open data layer</h2>
          <p className="panel-sub">Catalog only, no data storage · {scope}</p>
        </div>
      </div>

      {datasets.length === 0 && (
        <p className="muted">
          {nothingMissing
            ? "No missing data: nothing to look for."
            : "No catalogued dataset provides the missing data."}
        </p>
      )}

      {datasets.map((d) => (
        <article key={d.id} className="data-item">
          <div className="data-head">
            <h3 className="data-title">{d.label ?? d.id}</h3>
            {d.url && /^https?:\/\//.test(d.url) && (
              <a className="data-link" href={d.url} target="_blank" rel="noreferrer" title="Open the dataset page">
                ↗
              </a>
            )}
          </div>
          <div className="data-meta">
            {[names(d.publishers), names(d.coverage)].filter(Boolean).join(" · ")}
          </div>
          <div className="pills">
            {d.provides.map((v) => (
              <span key={v.id} className="pill">
                ✓ {v.label ?? v.id}
              </span>
            ))}
          </div>
        </article>
      ))}
    </section>
  );
}