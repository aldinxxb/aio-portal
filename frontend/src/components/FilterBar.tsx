import { useEffect, useState } from "react";
import { getOptions, type Draft, type Option } from "../api";
import type { Step } from "../steps";
import OptionButton from "./OptionButton";

type Props = {
  steps: Step[];                   // the wizard steps that produced the answers
  answers: Draft;                  // the current answers
  text: (id: string) => string;    // id -> readable name
  // called with the new answers (and the labels of any option just loaded)
  onChange: (answers: Draft, labels: Record<string, string>) => void;
};

// The answers shown as removable chips, each step with a "Change" button:
// the user adjusts one filter without going through the wizard again.
export default function FilterBar({ steps, answers, text, onChange }: Props) {
  const [openId, setOpenId] = useState<string | null>(null);   // the step being changed
  const [options, setOptions] = useState<Option[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);   // also the criteria left without an answer

  const open = steps.find((s) => s.id === openId) ?? null;
  const answersKey = JSON.stringify(answers);

  // Load the options of the open step (again after every change: the counts depend on the answers).
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    getOptions(open.id, answers)
      .then((found) => {
        if (!cancelled) setOptions(found);
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
  }, [openId, answersKey]);

  // A single-choice step that cannot be skipped (the challenge, the software) is the
  // starting point of everything else: it can only be changed with "Start again".
  const locked = (step: Step) => !step.multiple && !step.optional;

  function valuesOf(step: Step): string[] {
    const value = answers[step.field];
    if (value === undefined) return [];
    return Array.isArray(value) ? value : [value];
  }

  function setValues(step: Step, values: string[]) {
    const next = { ...answers, [step.field]: step.multiple ? values : values[0] } as Draft;
    if (!step.multiple && values.length === 0) delete next[step.field];
    const labels = Object.fromEntries(options.map((o) => [o.id, o.label ?? o.id]));
    onChange(next, labels);
  }

  function toggle(step: Step, id: string) {
    const current = valuesOf(step);
    if (current.includes(id)) setValues(step, current.filter((v) => v !== id));
    else setValues(step, step.multiple ? [...current, id] : [id]);
  }

  const unused = steps.filter((s) => valuesOf(s).length === 0 && s.id !== openId).length;

  return (
    <div className="filters">
      {steps.map((step) => {
        const values = valuesOf(step);
        if (values.length === 0 && !showAll && openId !== step.id) return null;
        return (
          <div key={step.id} className="filter">
            <span className="filter-title">{step.title}</span>
            {values.length === 0 && <span className="muted">no preference</span>}
            {values.map((id) => (
              <span key={id} className="chip">
                {text(id)}
                {!locked(step) && (
                  <button
                    className="chip-x"
                    title={`Remove ${text(id)}`}
                    onClick={() => setValues(step, values.filter((v) => v !== id))}
                  >
                    ×
                  </button>
                )}
              </span>
            ))}
            {!locked(step) && (
              <button
                className="filter-change"
                onClick={() => setOpenId(openId === step.id ? null : step.id)}
              >
                {openId === step.id ? "Done" : values.length ? "Change" : "Add"}
              </button>
            )}
          </div>
        );
      })}

      {(unused > 0 || showAll) && (
        <button className="filter-change filter-more" onClick={() => setShowAll(!showAll)}>
          {showAll ? "Hide the criteria without an answer" : `+ Refine with ${unused} more criteri${unused > 1 ? "a" : "on"}`}
        </button>
      )}

      {open && (
        <div className="filter-editor">
          <div className="filter-question">{open.question}</div>
          {loading && options.length === 0 && <p className="muted">Loading options…</p>}
          {error && <p className="error">{error}</p>}
          <div className="options">
            {options.map((option) => (
              <OptionButton
                key={option.id}
                option={option}
                selected={valuesOf(open).includes(option.id)}
                onClick={() => toggle(open, option.id)}
                countOf={open.countOf}
                relatedTitle={open.relatedTitle}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
