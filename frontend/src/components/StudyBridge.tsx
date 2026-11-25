import type { Entry } from "./EntryCards";
import type { Go } from "../searchIndex";
import { studyLine, toChallenge, toData, toSetup, type Study } from "../study";

// "Your study … Continue with it in": the same study, opened in another entry. Comparing what
// the entries say no longer means starting over.
const TARGETS: { id: Exclude<Entry, "ontology">; label: string; hint: string }[] = [
  { id: "data", label: "I have data", hint: "the open data of an area and what it makes possible" },
  { id: "software", label: "I have a model", hint: "check your own method or software for this study" },
  { id: "challenge", label: "I have a water problem", hint: "every workflow ranked for this study" },
];

export default function StudyBridge({ study, from, onGo }: { study: Study; from: Exclude<Entry, "ontology">; onGo: (go: Go) => void }) {
  if (!study.challenge) return null;
  const go = (id: Exclude<Entry, "ontology">) => onGo(id === "data" ? toData(study) : id === "software" ? toSetup(study) : toChallenge(study));
  return (
    <div className="bridge">
      <span className="bridge-study"><span className="bridge-label">Your study</span> {studyLine(study)}</span>
      <span className="bridge-go">
        <span className="muted">Continue with it in</span>
        {TARGETS.filter((t) => t.id !== from).map((t) => (
          <button key={t.id} className="btn bridge-btn" onClick={() => go(t.id)} title={t.hint}>{t.label}</button>
        ))}
      </span>
    </div>
  );
}
