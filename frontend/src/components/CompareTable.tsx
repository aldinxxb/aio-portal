import type { Result } from "../api";

const STATUS_TEXT = {
  directly_applicable: "Directly applicable",
  needs_complementary_data: "Needs complementary data",
  inputs_not_recorded: "Inputs not recorded",
} as const;

const percent = (value: number | null) =>
  value === null ? "–" : `${Math.round(value * 100)}%`;

const names = (items: { label: string }[]) =>
  items.length ? items.map((i) => i.label).join(", ") : "–";

// One row per criterion: a title and how to read it from a result.
const ROWS: { title: string; read: (r: Result) => string }[] = [
  { title: "Status", read: (r) => STATUS_TEXT[r.status] },
  { title: "Match", read: (r) => percent(r.score) },
  { title: "Input coverage", read: (r) => percent(r.input_coverage) },
  { title: "Process match", read: (r) => percent(r.process_match) },
  { title: "Processes modelled", read: (r) => r.processes.join(", ") },
  { title: "Inputs you have", read: (r) => names(r.inputs_available) },
  { title: "Inputs missing", read: (r) => names(r.inputs_missing) },
];

type Props = {
  results: Result[];
  onRemove: (id: string) => void;
};

export default function CompareTable({ results, onRemove }: Props) {
  if (results.length === 0) return null;

  return (
    <div className="table-wrap">
      <h3 className="group-title">Comparison</h3>
      <table className="compare">
        <thead>
          <tr>
            <th></th>
            {results.map((r) => (
              <th key={r.id}>
                {r.label ?? r.id}{" "}
                <button className="x-btn" onClick={() => onRemove(r.id)} title="Remove from comparison">
                  ×
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROWS.map((row) => (
            <tr key={row.title}>
              <th>{row.title}</th>
              {results.map((r) => (
                <td key={r.id}>{row.read(r)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}