import type { Recommendation, Ref } from "../api";

const name = (item: Ref) => item.label ?? item.id;

// One picture per output form.
const FORM_ICON: Record<string, string> = { MapForm: "🗺️", TimeSeriesForm: "📈", IndicatorForm: "🔢" };

type Props = { result: Recommendation };

// The expected outputs as cards: the question each answers, its form, then the chain
// output ← variable ← methods computing it, coloured like the diagnosis page
// (blue = expected output, violet = variable, amber = method).
// Below: the processes and water entities concerned, for information.
export default function ExpectedOutputs({ result }: Props) {
  const processes = result.related_processes;
  return (
    <div className="eo">
      {result.expected_outputs.length > 0 && (
        <>
          <div className="eo-head">
            <span className="eo-title">Your expected outputs</span>
            <span className="colour-key">
              <span><i className="key kind-output" /> output</span>
              <span><i className="key kind-variable" /> variable behind it</span>
              <span><i className="key kind-method" /> recommended methods computing it</span>
            </span>
          </div>
          <div className="eo-grid">
            {result.expected_outputs.map((output) => (
              <article key={output.id} className="eo-card">
                <div className="eo-card-head">
                  <span className="eo-icon">{FORM_ICON[output.forms[0]?.id] ?? "📄"}</span>
                  <div>
                    <div className="eo-name">{name(output)}</div>
                    <div className="eo-form">{output.forms.map(name).join(", ") || "form not recorded"}</div>
                  </div>
                </div>
                {output.question && <p className="eo-question">“{output.question}”</p>}
                <div className="eo-vars">
                  {output.variables.length === 0 && <span className="muted">no variable recorded</span>}
                  {output.variables.map((v) => (
                    <div key={v.id} className="eo-var">
                      <span className="eo-box kind-variable">{name(v)}</span>
                      <span className="eo-arrow">←</span>
                      {v.count > 0 ? (
                        <span className="eo-methods">
                          {v.computed_by.map((m) => <span key={m.id} className="eo-box kind-method">{name(m)}</span>)}
                          {v.count > v.computed_by.length && <span className="muted">+{v.count - v.computed_by.length} more</span>}
                        </span>
                      ) : v.derivable_from.length > 0 ? (
                        <span className="muted">derived from {v.derivable_from.map(name).join(", ")}</span>
                      ) : (
                        <span className="eo-box dg-bad">no recommended method computes it alone: see the workflows</span>
                      )}
                    </div>
                  ))}
                </div>
                {output.entities.length > 0 && (
                  <div className="eo-entities">For: {output.entities.map(name).join(", ")}</div>
                )}
              </article>
            ))}
          </div>
        </>
      )}

      <div className="eo-related">
        <div>
          <span className="eo-related-title">Processes concerned</span>
          <span className="muted">
            {" "}· {processes.source === "stated" ? "you chose them"
              : processes.source === "outputs" ? "those of the workflows delivering your outputs (no process step needed)"
              : "all processes of the challenge"}
          </span>
          <div className="pills">
            {processes.values.map((p) => (
              <span key={p.id} className={`pill${processes.primary.includes(p.id) ? " pill-hit" : ""}`}
                    title={processes.primary.includes(p.id) ? "a main process of the challenge" : undefined}>
                {name(p)}
              </span>
            ))}
          </div>
        </div>
        {result.related_entities.length > 0 && (
          <div>
            <span className="eo-related-title">Water entities concerned</span>
            <span className="muted"> · for information</span>
            <div className="pills">
              {result.related_entities.map((e) => (
                <span key={e.id} className="pill" title={`relevant for: ${e.outputs.join(", ")}`}>
                  {name(e)} <span className="muted">· {e.outputs.length}</span>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
