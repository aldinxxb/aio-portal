import { useEffect, useState } from "react";
import { getOptions, type Draft, type Option } from "../api";
import type { Step } from "../steps";
import OptionButton from "./OptionButton";

type Props = {
  steps: Step[];                                                // the questions to ask, in order
  onFinish: (draft: Draft, labels: Record<string, string>) => void; // final answers + id -> label
};

export default function Wizard({ steps, onFinish }: Props) {
  const [stepIndex, setStepIndex] = useState(0);
  const [draft, setDraft] = useState<Draft>({});
  const [options, setOptions] = useState<Option[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const step = steps[stepIndex];

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getOptions(step.id, draft)
      .then((result) => {
        if (cancelled) return;
        setOptions(result);
        setLabels((previous) => ({
          ...previous,
          ...Object.fromEntries(result.map((o) => [o.id, o.label ?? o.id])),
        }));
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
  }, [stepIndex]);

  // the next step that is asked with these answers (a step may be skipped, see Step.skipWhen)
  const skipped = (index: number, answers: Draft) => !!steps[index].skipWhen?.(answers);

  function confirm(values: string[]) {
    const next = { ...draft, [step.field]: step.multiple ? values : values[0] } as Draft;
    let target = stepIndex + 1;
    while (target < steps.length && skipped(target, next)) {
      delete next[steps[target].field];
      target++;
    }
    setDraft(next);
    setSelected([]);
    if (target < steps.length) {
      setStepIndex(target);
    } else {
      onFinish(next, labels);
    }
  }

  function handleClick(id: string) {
    if (!step.multiple) {
      confirm([id]);
    } else {
      setSelected(
        selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id]
      );
    }
  }

  function goBack() {
    let target = stepIndex - 1;
    while (target > 0 && skipped(target, draft)) target--;
    const previous = draft[steps[target].field];
    const kept = { ...draft };
    for (let i = target; i < steps.length; i++) {
      delete kept[steps[i].field];
    }
    setDraft(kept);
    setSelected(previous === undefined ? [] : Array.isArray(previous) ? previous : [previous]);
    setStepIndex(target);
  }

  // Readable text for one answered step, e.g. "runoff, infiltration"
  function answerText(field: keyof Draft): string {
    const value = draft[field];
    if (value === undefined) return "no preference";   // an optional step that was skipped
    const ids = Array.isArray(value) ? value : [value];
    return ids.length ? ids.map((id) => labels[id] ?? id).join(", ") : "no preference";
  }

  return (
    <section className="panel">
      <ol className="stepper">
        {steps.map((s, i) => {
          const off = i !== stepIndex && skipped(i, draft);
          return (
            <li key={s.id} className={`step${i === stepIndex ? " active" : off ? " skipped" : i < stepIndex ? " done" : ""}`}
                title={off ? s.skipNote : undefined}>
              {i + 1}. {s.title}{off && s.skipNote ? ` · ${s.skipNote}` : ""}
            </li>
          );
        })}
      </ol>

      {stepIndex > 0 && (
        <div className="answers">
          {steps.slice(0, stepIndex).map((s, i) => (
            <span key={s.id}>
              <span className="muted">{s.title}:</span>{" "}
              <strong>{skipped(i, draft) ? s.skipNote ?? "skipped" : answerText(s.field)}</strong>
            </span>
          ))}
        </div>
      )}

      <h2 className="question">{step.question}</h2>

      {loading && <p className="muted">Loading options…</p>}
      {error && <p className="error">{error}</p>}

      {!loading && (
        <div className="options">
          {options.map((option) => (
            <OptionButton
              key={option.id}
              option={option}
              selected={step.multiple ? selected.includes(option.id) : false}
              countOf={step.countOf}
              relatedTitle={step.relatedTitle}
              onClick={() => handleClick(option.id)}
            />
          ))}
        </div>
      )}

      <div className="actions">
        {stepIndex > 0 && (
          <button className="btn" onClick={goBack}>
            Back
          </button>
        )}
        {step.multiple && (
          <button className="btn btn-primary" onClick={() => confirm(selected)}>
            {selected.length ? "Next" : "Next (no preference)"}
          </button>
        )}
        {!step.multiple && step.optional && (
          <button className="btn btn-primary" onClick={() => confirm([])}>
            Skip (no preference)
          </button>
        )}
      </div>
    </section>
  );
}