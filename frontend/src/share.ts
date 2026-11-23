// Shareable addresses and saved drafts.
//
// Every entry keeps its study in the address, so a reload keeps it and a copied link opens
// the same study for a colleague:
//
//   #/data?s=<state>                  Start from data
//   #/setup?s=<state>                 Start from a modeling approach
//   #/challenge?s=<state>             Start from a water challenge
//   #/…&diagnosis=<set-up>            a workflow's diagnosis opened from the results
//   #/ontology/<term>                 the ontology (handled by its own page)
//
// <state> is the entry's state as JSON, compacted (empty values dropped) and base64url-encoded.
// The same state is kept per entry in the browser as a draft, offered back when the portal is
// opened without one in the address.

import type { Entry } from "./components/EntryCards";
import { EMPTY_REQUEST, type SetupRequest } from "./setupApi";
import type { DataItem } from "./dataApi";

const ROUTES: Record<Exclude<Entry, "ontology">, string> = { data: "data", software: "setup", challenge: "challenge" };

export type Shared = { entry: Entry; state: unknown | null; diagnosis: unknown | null; term: string | null };

// ---- encoding ---------------------------------------------------------------------------

// drop what carries nothing (null, empty strings, lists and objects): shorter links
function compact(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(compact);
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value)) {
      const c = compact(v);
      if (c === null || c === undefined || c === "" || (typeof c === "object" && !Array.isArray(c) && Object.keys(c as object).length === 0)) continue;
      if (Array.isArray(c) && c.length === 0) continue;
      out[k] = c;
    }
    return out;
  }
  return value;
}

export function encode(value: unknown): string {
  const bytes = new TextEncoder().encode(JSON.stringify(compact(value)));
  let text = "";
  for (const b of bytes) text += String.fromCharCode(b);
  return btoa(text).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function decode<T>(text: string | null): T | null {
  if (!text) return null;
  try {
    const raw = atob(text.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(new TextDecoder().decode(Uint8Array.from(raw, (c) => c.charCodeAt(0)))) as T;
  } catch {
    return null;   // a damaged link opens the entry empty rather than failing
  }
}

// ---- the address ------------------------------------------------------------------------

export function readAddress(hash = window.location.hash): Shared {
  const onto = hash.match(/^#\/ontology\/?(.*)$/);
  if (onto) return { entry: "ontology", state: null, diagnosis: null, term: onto[1] ? decodeURIComponent(onto[1]) : null };
  const m = hash.match(/^#\/(data|setup|challenge)(?:\?(.*))?$/);
  if (!m) return { entry: "data", state: null, diagnosis: null, term: null };
  const entry = (Object.keys(ROUTES) as (keyof typeof ROUTES)[]).find((k) => ROUTES[k] === m[1])!;
  const params = new URLSearchParams(m[2] ?? "");
  return { entry, state: decode(params.get("s")), diagnosis: decode(params.get("diagnosis")), term: null };
}

export function addressOf(entry: Entry, state: unknown | null, diagnosis: unknown | null = null): string {
  if (entry === "ontology") return "#/ontology";
  const params = new URLSearchParams();
  if (state) params.set("s", encode(state));
  if (diagnosis) params.set("diagnosis", encode(diagnosis));
  const query = params.toString();
  return `#/${ROUTES[entry]}${query ? `?${query}` : ""}`;
}

// replace the address without a new history step (typing an answer is not a page)
export function writeAddress(hash: string) {
  if (window.location.hash === hash) return;
  window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search + hash);
}

// ---- drafts -----------------------------------------------------------------------------

export type Draft = { state: unknown; saved: number; summary: string };

const key = (entry: Entry) => `aio-draft-${entry}`;

export function saveDraft(entry: Entry, state: unknown, summary: string) {
  try { localStorage.setItem(key(entry), JSON.stringify({ state, saved: Date.now(), summary })); } catch { /* private window */ }
}

export function loadDraft(entry: Entry): Draft | null {
  try {
    const raw = localStorage.getItem(key(entry));
    return raw ? (JSON.parse(raw) as Draft) : null;
  } catch {
    return null;
  }
}

export function dropDraft(entry: Entry) {
  try { localStorage.removeItem(key(entry)); } catch { /* private window */ }
}

export function ago(time: number): string {
  const minutes = Math.round((Date.now() - time) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return new Date(time).toLocaleDateString();
}

// ---- restoring: links drop empty values, so put the full shapes back --------------------


type Partial2<T> = { [K in keyof T]?: T[K] extends object ? Partial<T[K]> : T[K] };

export function fullSetupRequest(value: unknown): SetupRequest | null {
  if (!value || typeof value !== "object") return null;
  const v = value as Partial2<SetupRequest>;
  return {
    setup: { ...EMPTY_REQUEST.setup, ...(v.setup ?? {}) },
    context: { ...EMPTY_REQUEST.context, ...(v.context ?? {}) },
    data: ((v.data as Partial<SetupRequest["data"][number]>[] | undefined) ?? []).map((d) => ({
      variable: d.variable ?? "", source: d.source ?? "own", dataset: d.dataset ?? null, step: d.step ?? null, resolution_m: d.resolution_m ?? null,
    })).filter((d) => d.variable),
  };
}

export function fullDataItems(value: unknown): DataItem[] {
  if (!Array.isArray(value)) return [];
  return (value as Partial<DataItem>[]).filter((d) => d && d.variable).map((d) => ({
    variable: d.variable!, source: d.source ?? "own", dataset: d.dataset ?? null, step: d.step ?? null,
    start: d.start ?? null, end: d.end ?? null, form: d.form ?? null,
  }));
}
