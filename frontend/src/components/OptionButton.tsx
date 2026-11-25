import type { Option } from "../api";

type Props = {
  option: Option;          // the data to show (label, count, enabled, reason, hint)
  selected: boolean;       // is it currently picked?
  onClick: () => void;     // what to do when clicked (decided by the wizard)
  countOf?: string;        // what the number counts, shown when the mouse is over it
  relatedTitle?: string;   // name of the option's "related" list
};

// "method(s) still possible…" -> "methods" (or "method" for one): the unit shown with the number
const unitOf = (countOf: string, n: number) => countOf.split(" ")[0].replace("(s)", n === 1 ? "" : "s");

export default function OptionButton({
  option,
  selected,
  onClick,
  countOf = "method(s)",
  relatedTitle = "Related",
}: Props) {
  return (
    <div className="opt-wrap">
      <button
        className={`opt${selected ? " selected" : ""}${option.suggested ? " opt-direct" : ""}`}
        onClick={onClick}
        disabled={!option.enabled}
        title={option.reason ?? ""}
      >
        <span>{option.label ?? option.id}</span>
        {option.suggested && (
          <span className="opt-star" title="Suggested by the ontology">★</span>
        )}
        <span className="count" title={`${option.count} ${countOf}`}>
          {option.count}<span className="count-unit"> {unitOf(countOf, option.count)}</span>
        </span>
      </button>
      {option.hint && <div className="opt-hint">{option.hint}</div>}
      {option.related.length > 0 && (
        <div className="opt-related">
          {relatedTitle}: {option.related.map((r) => r.label ?? r.id).join(", ")}
        </div>
      )}
      {!option.enabled && option.reason && <div className="opt-reason">{option.reason}</div>}
    </div>
  );
}
