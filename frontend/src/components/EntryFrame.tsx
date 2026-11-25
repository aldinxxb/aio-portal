import type { ReactNode } from "react";

// The frame shared by the three entries: a header saying what the entry answers, the numbered
// pages of its flow, and a bar fixed at the bottom of the screen to move between them. Every
// entry reads and moves the same way: one page at a time.

export type Hero = { kicker: string; title: string; lead: string };

// compact: after the first page, one line instead of the full banner (the page needs the room)
export function EntryHero({ kicker, title, lead, aside, compact = false }: Hero & { aside?: ReactNode; compact?: boolean }) {
  if (compact) {
    return (
      <div className="ehero compact">
        <div className="ehero-line">
          <span className="ehero-kicker">{kicker}</span>
          <span className="ehero-title">{title}</span>
        </div>
        {aside && <div className="ehero-aside">{aside}</div>}
      </div>
    );
  }
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

export function PageSteps({ steps, current, reachable, onGo, note }: {
  steps: PageStep[];
  current: number;
  reachable: (index: number) => boolean;   // a page can be opened once the ones before are filled in
  onGo: (index: number) => void;
  note?: ReactNode;                        // a line under the steps (e.g. what is left for later)
}) {
  return (
    <>
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
      {note && <p className="psteps-note">{note}</p>}
    </>
  );
}

// The bar at the bottom of a page, fixed to the bottom of the screen while the page is in view:
// Back on the left, the study so far in the middle, Next on the right (with why it is not
// possible yet, when it is not).
export function PageNav({ onBack, onNext, nextLabel = "Next", nextDisabled, note, summary, quiet = false }: {
  onBack?: () => void; onNext?: () => void; nextLabel?: string; nextDisabled?: boolean;
  note?: ReactNode;      // a word next to Next (why it is not possible yet, or what it will do)
  summary?: ReactNode;   // the study so far, in one line
  quiet?: boolean;       // Next is a secondary action (e.g. "Start again")
}) {
  return (
    <div className="pnav">
      {onBack ? <button className="btn" onClick={onBack}>Back</button> : <span className="pnav-gap" />}
      <span className="pnav-summary">{summary}</span>
      {note && <span className="muted pnav-note">{note}</span>}
      {onNext && <button className={`btn${quiet ? "" : " btn-primary"}`} disabled={nextDisabled} onClick={onNext}>{nextLabel}</button>}
    </div>
  );
}
