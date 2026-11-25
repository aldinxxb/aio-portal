// How workflows are weighed for the user: what is left to find, and why one is the best match.
import type { Chain, Ref } from "./api";

const name = (item: Ref) => item.label ?? item.id;

export const count = (c: Chain, state: string) => c.inputs.filter((i) => i.state === state).length;
export const toFind = (c: Chain) => count(c, "open_data") + 2 * count(c, "missing");   // a missing input weighs more

// Why this workflow is the best match: its strong points, compared with the others listed.
export function whyBest(best: Chain, all: Chain[]): string[] {
  const runnable = all.filter((c) => c.status === "runnable");
  const why: string[] = [];
  if (best.kind === "reference") why.push("standard practice");
  if (count(best, "missing") === 0) why.push(count(best, "open_data") === 0 ? "all its data in your hands" : "nothing left without a source");
  const fetch = count(best, "open_data");
  if (fetch > 0 && runnable.length > 1 && runnable.every((c) => count(c, "open_data") >= fetch)) why.push(`the least data to fetch (${fetch})`);
  if (best.coverage !== null && best.coverage >= 0.999) why.push("covers every main process");
  if (best.software.length === 1) why.push(`one software (${name(best.software[0])})`);
  if (best.all_open) why.push("open source");
  return why.slice(0, 3);
}
