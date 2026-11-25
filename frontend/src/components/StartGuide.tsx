import { useEffect, useRef } from "react";
import type { Entry } from "./EntryCards";
import { CARDS } from "../entries";
import { challengeGo, dataGo, setupGo, type Go } from "../searchIndex";

// "Where do you want to start?": the three starting points side by side, each with the kind of
// question it answers and examples that open it already filled in. Shown on a first visit, and
// again from "Where to start?" in the app bar.

type Example = { text: string; go: Go };
const flood = { id: "Flood", label: "flood" };
const drought = { id: "Drought", label: "drought" };

const STARTS: { id: Exclude<Entry, "ontology">; who: string; examples: Example[] }[] = [
  {
    id: "data",
    who: "You hold observations or maps (rainfall, discharge, land cover…) for a place in France.",
    examples: [
      { text: "I have daily rainfall and discharge from my stations",
        go: dataGo([{ id: "Precipitation", label: "precipitation", static: false }, { id: "Discharge", label: "discharge", static: false }]) },
      { text: "I only have rainfall: what else can I use?",
        go: dataGo([{ id: "Precipitation", label: "precipitation", static: false }]) },
    ],
  },
  {
    id: "software",
    who: "You already use a model, a method or a software and want to know if it fits your study.",
    examples: [
      { text: "I use HEC-HMS: does it fit a flood study?", go: setupGo({ software: "HEC-HMS" }, flood) },
      { text: "I use SWAT for a drought study", go: setupGo({ software: "SWAT" }, drought) },
    ],
  },
  {
    id: "challenge",
    who: "You start from an issue (flood, drought, water quality…) and the result you need.",
    examples: [
      { text: "I need a flood hazard map", go: challengeGo(flood, [{ id: "FloodHazardMap", label: "flood hazard map", question: null, challenge: flood }]) },
      { text: "How low will the river get in a drought?", go: challengeGo(drought, [{ id: "LowFlowIndicator", label: "low-flow indicator", question: null, challenge: drought }]) },
    ],
  },
];

export default function StartGuide({ onStart, onGo, onClose }: {
  onStart: (entry: Entry) => void; onGo: (go: Go) => void; onClose: () => void;
}) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="guide-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="guide" role="dialog" aria-modal="true" aria-labelledby="guide-title" tabIndex={-1} ref={panel}>
        <button className="guide-close" onClick={onClose} aria-label="Close" title="Close (Esc)">×</button>
        <div className="guide-head">
          <h2 id="guide-title">Where do you want to start?</h2>
          <p>The portal recommends hydrological models and the open data to run them. Pick the situation closest to yours, or try an example.</p>
        </div>
        <div className="guide-cards">
          {STARTS.map((start) => {
            const card = CARDS.find((c) => c.id === start.id)!;
            return (
              <section key={start.id} className="guide-card">
                <div className="guide-card-head">
                  <span className="entry-icon">{card.icon}</span>
                  <div>
                    <h3>{card.title}</h3>
                    <span className="guide-q">{card.text}</span>
                  </div>
                </div>
                <p className="guide-who">{start.who}</p>
                <div className="guide-examples">
                  <span className="guide-label">For example</span>
                  {start.examples.map((ex) => (
                    <button key={ex.text} className="guide-example" onClick={() => onGo(ex.go)}>“{ex.text}”</button>
                  ))}
                </div>
                <button className="btn btn-primary guide-start" onClick={() => onStart(start.id)}>Start here</button>
              </section>
            );
          })}
        </div>
        <div className="guide-foot">
          <span>You can also <strong>type your question</strong> in the search box at the top, or{" "}
            <button className="link-btn" onClick={() => onStart("ontology")}>explore the ontology</button> behind the recommendations.</span>
          <button className="link-btn" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
