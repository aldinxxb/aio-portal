import { useEffect, useState } from "react";
import { getOptions, type Draft, type Option } from "../api";
import type { Step } from "../steps";
import OptionButton from "./OptionButton";
import { EntryHero, PageNav, PageSteps, type Hero } from "./EntryFrame";

// A start from the search or an example: answers already given (asked no more), and choices
// ticked in advance on a later question (the user still confirms them there).
export type WizardStart = { draft: Draft; labels: Record<string, string>; preselect: Partial<Draft> };

type Props = {
  steps: Step[];                                                // the questions to ask, in order
  onFinish: (draft: Draft, labels: Record<string, string>) => void; // final answers + id -> label
  initial?: WizardStart | null;
  hero?: Hero;                        // the entry's banner (full on the first question, then one line)
  later?: string[];                   // the questions left for "Refine" on the results page
};

const asList = (value: unknown): string[] => (value === undefined || value === null ? [] : Array.isArray(value) ? value : [String(value)]);

export default function Wizard({ steps, onFinish, initial, hero, later = [] }: Props) {
  // the first question not answered yet
  const [stepIndex, setStepIndex] = useState(() => {
    if (!initial) return 0;
    const i = steps.findIndex((s) => initial.draft[s.field] === undefined);
    return i < 0 ? 0 : i;
  });
  const [draft, setDraft] = useState<Draft>(initial?.draft ?? {});
  const [options, setOptions] = useState<Option[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [labels, setLabels] = useState<Record<string, string>>(initial?.labels ?? {});
  const preselect = initial?.preselect ?? {};
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const step = steps[stepIndex];

  // a question with choices ticked in advance: tick them (unless the user already chose)
  useEffect(() => {
    const ahead = asList(preselect[step.field]);
    if (ahead.length && step.multiple) setSelected((now) => (now.length ? now : ahead));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stepIndex]);

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
    goTo(target);
  }

  // an earlier question, from the step bar: its answer and the later ones are asked again
  function goTo(target: number) {
    if (target >= stepIndex) return;
    const previous = draft[steps[target].field];
    const kept = { ...draft };
    for (let i = target; i < steps.length; i++) {
      delete kept[steps[i].field];
    }
    setDraft(kept);
    setSelected(previous === undefined ? [] : Array.isArray(previous) ? previous : [previous]);
    setStepIndex(target);
  }

  // the answers so far, in one line for the bottom bar
  const summary = steps.slice(0, stepIndex).filter((_, i) => !skipped(i, draft) && draft[steps[i].field] !== undefined)
    .map((s) => answerText(s.field)).filter((t) => t !== "no preference").join(" · ");
  const last = (() => { let i = stepIndex + 1; while (i < steps.length && skipped(i, draft)) i++; return i >= steps.length; })();

  // Readable text for one answered step, e.g. "runoff, infiltration"
  function answerText(field: keyof Draft): string {
    const value = draft[field];
    if (value === undefined) return "no preference";   // an optional step that was skipped
    const ids = Array.isArray(value) ? value : [value];
    return ids.length ? ids.map((id) => labels[id] ?? id).join(", ") : "no preference";
  }

  return (
    <>
    {hero && <EntryHero {...hero} compact={stepIndex > 0} />}
    <section className="panel">
      <PageSteps
        steps={steps.map((s) => ({ title: s.title, sub: s.sub }))}
        current={stepIndex}
        reachable={(i) => i <= stepIndex}
        onGo={goTo}
        note={later.length ? <>{steps.length} questions, then the workflows. {later.join(", ").replace(/^./, (c) => c.toUpperCase())}: add them on the results page with <strong>Refine</strong>, if you need them.</> : undefined}
      />

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

      <PageNav
        onBack={stepIndex > 0 ? goBack : undefined}
        summary={summary}
        onNext={step.multiple ? () => confirm(selected) : step.optional ? () => confirm([]) : undefined}
        nextLabel={step.multiple
          ? (last ? "See the workflows" : selected.length ? "Next" : "Next (no preference)")
          : "Skip (no preference)"}
        note={!step.multiple && !step.optional ? "choose one to go on" : step.multiple ? (selected.length ? `${selected.length} chosen` : "optional") : undefined}
      />
    </section>
    </>
  );
}