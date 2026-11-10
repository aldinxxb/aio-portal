import type { Option } from "../api";

type Props = {
  option: Option;          // the data to show (label, count, enabled, reason)
  selected: boolean;       // is it currently picked?
  onClick: () => void;     // what to do when clicked (decided by the wizard)
};

export default function OptionButton({ option, selected, onClick }: Props) {
  return (
    <div className="opt-wrap">
      <button
        className={`opt${selected ? " selected" : ""}`}
        onClick={onClick}
        disabled={!option.enabled}
        title={option.reason ?? ""}
      >
        <span>{option.label ?? option.id}</span>
        <span className="count">{option.count}</span>
      </button>
      {!option.enabled && option.reason && <div className="opt-reason">{option.reason}</div>}
    </div>
  );
}