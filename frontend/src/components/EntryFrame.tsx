import type { ReactNode } from "react";

// The frame shared by the three entries: a header saying what the entry answers, and the
// numbered pages of its flow. Every entry reads the same way: one page at a time.

export function EntryHero({ kicker, title, lead, aside }: { kicker: string; title: string; lead: string; aside?: ReactNode }) {
  return (
    <div className="ehero">
      <div>
        <div className="ehero-kicker">{kicker}</div>
        <h2 className="ehero-title">{title}</h2>
        <p className="ehero-lead">{lead}</p>
      </div>
      {aside && <div className="ehero-aside">{aside}</div>}
    </div>
  );
}

export type PageStep = { title: string; sub?: string };

export function PageSteps({ steps, current, reachable, onGo }: {
  steps: PageStep[];
  current: number;
  reachable: (index: number) => boolean;   // a page can be opened once the ones before are filled in
  onGo: (index: number) => void;
}) {
  return (
    <ol className="psteps">
      {steps.map((step, i) => (
        <li key={step.title}>
          <button className={`pstep${i === current ? " on" : i < current ? " done" : ""}`}
                  disabled={!reachable(i)} aria-current={i === current ? "step" : undefined} onClick={() => onGo(i)}>
            <span className="pstep-n">{i < current ? "✓" : i + 1}</span>
            <span className="pstep-text">
              <span className="pstep-title">{step.title}</span>
              {step.sub && <span className="pstep-sub">{step.sub}</span>}
            </span>
          </button>
        </li>
      ))}
    </ol>
  );
}

// "Back" and "Next" at the bottom of a page
export function PageNav({ onBack, onNext, nextLabel = "Next", nextDisabled, note }: {
  onBack?: () => void; onNext?: () => void; nextLabel?: string; nextDisabled?: boolean; note?: ReactNode;
}) {
  return (
    <div className="pnav">
      {onBack ? <button className="btn" onClick={onBack}>Back</button> : <span />}
      {note && <span className="muted pnav-note">{note}</span>}
      {onNext && <button className="btn btn-primary" disabled={nextDisabled} onClick={onNext}>{nextLabel}</button>}
    </div>
  );
}
