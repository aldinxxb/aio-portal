import type { Result, Status } from "../api";

const STATUS_CLASS: Record<Status, string> = {
  directly_applicable: "is-direct",
  needs_complementary_data: "is-complement",
  inputs_not_recorded: "is-unknown",
};

type Props = {
  result: Result;
  text: (id: string) => string;   // id -> readable name
  compareMode: boolean;           // show the Compare tick box?
  compared: boolean;              // is this method in the comparison?
  canCompare: boolean;            // is there still room (max 3)?
  onToggleCompare: () => void;
};

export default function ResultCard({ result, text, compareMode, compared, canCompare, onToggleCompare }: Props) {
  const hasScore = result.score !== null;

  return (
    <article className={`result ${STATUS_CLASS[result.status]}`}>
      <div>
        <h3 className="result-title">{result.label ?? result.id}</h3>
        <div className="result-sub">{result.processes.map(text).join(" + ")}</div>

        <div className="pills">
          {result.inputs_available.map((i) => (
            <span key={i.id} className="pill">
              ✓ {i.label ?? i.id}
            </span>
          ))}
          {result.inputs_missing.map((i) => (
            <span key={i.id} className="pill pill-warn">
              ⚠ {i.label ?? i.id}
            </span>
          ))}
        </div>

        <p className="result-note">{result.explanation}</p>

        {compareMode && (
          <label className="compare-box">
            <input
              type="checkbox"
              checked={compared}
              disabled={!compared && !canCompare}
              onChange={onToggleCompare}
            />
            Compare
          </label>
        )}
      </div>

      <div className={`match${hasScore ? "" : " none"}`}>
        <span className="match-label">Match</span>
        <span className="match-value">{hasScore ? `${Math.round(result.score! * 100)}%` : "–"}</span>
      </div>
    </article>
  );
}