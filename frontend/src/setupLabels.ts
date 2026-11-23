// Words shared by the pages of the Modeling Approach entry.
import type { Ref } from "./api";
import type { DataRow, Derivation, Nature } from "./setupApi";

export const name = (item: Ref) => item.label ?? item.id;
export const names = (items: Ref[]) => items.map(name).join(", ");

export const NATURE: Record<Nature, string> = {
  forcing: "forcing",
  boundary: "boundary condition",
  static: "static description",
  initial: "initial state",
};
export const KIND: Record<DataRow["kind"], string> = {
  mandatory: "required input",
  optional: "optional input",
  calibration: "calibration data",
  initial: "initial state",
  parameter: "parameter",
};
export const STATUS: Record<DataRow["status"], { text: string; css: string }> = {
  in_hand: { text: "you have it", css: "pill-hit" },
  available: { text: "open data available", css: "pill-open" },
  derivable: { text: "can be derived", css: "pill-open" },
  needs_component: { text: "another method must compute it", css: "pill-warn" },
  missing: { text: "no source", css: "pill-warn" },
  unused: { text: "not used", css: "" },
  initial_state: { text: "warm-up or snapshot", css: "pill-internal" },
};

export const derivationText = (d: Derivation) =>
  `from ${names(d.from)}${d.how ? ` (${d.how})` : ""}`;

// Where a piece of data comes from, in one short sentence.
export function sourceOf(row: DataRow): string {
  const step = row.step_ref ? ` (${name(row.step_ref)})` : "";
  switch (row.status) {
    case "in_hand":
      return row.dataset ? `${name(row.dataset)}${step}` : `your own data${step}`;
    case "available":
      return row.datasets.length
        ? `not chosen yet · open data: ${row.datasets.slice(0, 2).map(name).join(", ")}${row.datasets.length > 2 ? "…" : ""}`
        : "not chosen yet · open data exists";
    case "derivable":
      return row.derivations.length ? `to derive ${derivationText(row.derivations[0])}` : `to derive from ${names(row.derived_from)}`;
    case "needs_component":
      return "no source · another method must compute it";
    case "missing":
      return "no source";
    case "unused":
      return "not used";
    case "initial_state":
      return "warm-up period or observed snapshot";
  }
}
