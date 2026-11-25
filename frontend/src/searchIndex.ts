// What the header search knows, and where each match takes the user.
//
// The search reads a question in plain words ("flood hazard map with my rainfall data") and
// proposes where to go, each suggestion opening an entry already filled in:
//   a water challenge or an expected output   ->  "I have a water problem", those answers given
//   a variable                                ->  "I have data", that variable declared
//   a software or a standard workflow         ->  "I have a model", that set-up chosen
//   anything else                             ->  the ontology, searched for the words
// The lists come from the portal's own vocabulary (the same ones the entries use), loaded once.

import { getChallengeOutputs, getChallenges, type Draft } from "./api";
import { getDeclarable } from "./dataApi";
import { EMPTY_REQUEST, setupOptions, type SetupOption } from "./setupApi";
import type { DataState } from "./components/DataEntry";
import type { SetupState } from "./components/SetupEntry";

// ---- where a suggestion goes ------------------------------------------------------------

export type Go =
  | { kind: "challenge"; draft: Draft; labels: Record<string, string>; preselect: Partial<Draft> }
  | { kind: "data"; state: DataState }
  | { kind: "setup"; state: SetupState }
  | { kind: "ontology"; query: string };

export type Suggestion = { key: string; group: string; title: string; detail: string | null; go: Go };

type Item = { id: string; label: string };
type Output = Item & { question: string | null; challenge: Item };
type Variable = Item & { static: boolean };
type Chain = Item & { methods: string[]; challenges: Item[] };
export type Index = { challenges: Item[]; outputs: Output[]; variables: Variable[]; software: Item[]; chains: Chain[] };

let loading: Promise<Index> | null = null;

// loaded on the first use of the search, then kept
export function loadIndex(): Promise<Index> {
  if (!loading) {
    loading = (async () => {
      const [challenges, variables, software, chains] = await Promise.all([
        getChallenges(),
        getDeclarable().catch(() => []),
        setupOptions<{ options: SetupOption[] }>("software", EMPTY_REQUEST).then((r) => r.options).catch(() => []),
        setupOptions<{ options: SetupOption[] }>("reference_chain", EMPTY_REQUEST).then((r) => r.options).catch(() => []),
      ]);
      const named = challenges.map((c) => ({ id: c.id, label: c.label ?? c.id }));
      const outputs = (await Promise.all(named.map((c) =>
        getChallengeOutputs(c.id).then((list) => list.map((o) => ({ id: o.id, label: o.label, question: o.question, challenge: c }))).catch(() => []),
      ))).flat();
      return {
        challenges: named,
        outputs,
        variables: variables.map((v) => ({ id: v.id, label: v.label ?? v.id, static: v.static })),
        software: software.map((s) => ({ id: s.id, label: s.label ?? s.id })),
        chains: chains.map((c) => ({
          id: c.id, label: c.label ?? c.id, methods: (c.methods ?? []).map((m) => m.id),
          challenges: (c.challenges ?? []).map((x) => ({ id: x.id, label: x.label ?? x.id })),
        })),
      };
    })().catch((e) => { loading = null; throw e; });
  }
  return loading;
}

// ---- matching ----------------------------------------------------------------------------

const plain = (text: string) =>
  ` ${text.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, " ").trim()} `;

// everyday words for the portal's terms
const SYNONYMS: [RegExp, string][] = [
  [/ (rain|rainfall|rainfalls|pluie|pluviometrie) /g, " precipitation "],
  [/ (streamflow|river flow|flow rate|debit|runoff data) /g, " discharge "],
  [/ (flooding|floods|inundation|inondation|crue|crues) /g, " flood "],
  [/ (droughts|secheresse|low flow|low flows|etiage) /g, " drought "],
  [/ (temperature|temperatures) /g, " air temperature "],
  [/ (risk map|hazard) /g, " flood hazard map "],
  [/ (pollution|pollutant|pollutants) /g, " water quality "],
];
const STOP = new Set("a an the of for in on at to with and or my our i we need want have do does what which how is are data model models study".split(" "));

function expand(query: string): string {
  let q = plain(query);
  for (const [re, to] of SYNONYMS) q = q.replace(re, (m) => `${m}${to.trim()} `);
  return q;
}

// how well a label fits the query: the label named in the question (best), or the words typed
// so far found in the label (while typing)
function score(label: string, query: string, typed: string[]): number {
  const l = plain(label);
  if (query.includes(l)) return 100 + l.length;
  if (typed.length && typed.every((w) => l.includes(` ${w}`))) return 40 + (typed.length * 10) - l.length / 10;
  return 0;
}

function best<T extends Item>(items: T[], query: string, typed: string[], limit: number): T[] {
  return items.map((item) => ({ item, s: score(item.label, query, typed) }))
    .filter((x) => x.s > 0).sort((a, b) => b.s - a.s).slice(0, limit).map((x) => x.item);
}

// ---- the suggestions -----------------------------------------------------------------------

export const challengeGo = (challenge: Item, outputs: Output[] = [], variables: Variable[] = []): Go => ({
  kind: "challenge",
  draft: { challenge: challenge.id },
  labels: { [challenge.id]: challenge.label, ...Object.fromEntries([...outputs, ...variables].map((x) => [x.id, x.label])) },
  preselect: { outputs: outputs.map((o) => o.id), available_variables: variables.map((v) => v.id) },
});

export const dataGo = (variables: Variable[]): Go => ({
  kind: "data",
  state: {
    page: 0,
    data: variables.map((v) => ({
      variable: v.id, source: "own", dataset: null, step: v.static ? null : "Daily",
      start: null, end: null, form: v.static ? "map" : "series",
    })),
  },
});

export const setupGo = (setup: Partial<SetupState["request"]["setup"]>, challenge: Item | null): Go => ({
  kind: "setup",
  state: {
    step: setup.reference_chain ? 1 : 0,
    request: {
      ...EMPTY_REQUEST,
      setup: { ...EMPTY_REQUEST.setup, ...setup },
      context: { ...EMPTY_REQUEST.context, challenge: challenge?.id ?? null },
    },
  },
});

const names = (items: Item[]) => items.map((x) => x.label).join(", ");

export function suggest(index: Index, text: string): Suggestion[] {
  const query = expand(text);
  const typed = plain(text).trim().split(" ").filter((w) => w.length >= 3 && !STOP.has(w));
  if (!typed.length && query.trim().length < 3) return [];

  const outputs = best(index.outputs, query, typed, 3);
  // a variable that is only part of an output's name ("soil moisture" in "soil moisture map") is
  // not data the user said they have
  const named = best(index.variables, query, typed, 3);
  const variables = named
    .filter((v) => !outputs.some((o) => plain(o.label).includes(plain(v.label)) && plain(o.label) !== plain(v.label)));
  const software = best(index.software, query, typed, 2);
  const chains = best(index.chains, query, typed, 2);
  // the challenge: one named, else the one of the output found
  const challenges = best(index.challenges, query, typed, 2);
  const challenge = challenges[0] ?? outputs[0]?.challenge ?? null;
  const out: Suggestion[] = [];

  // 1. the whole question at once: a challenge (and its outputs, and the data named)
  if (challenge) {
    const theirs = outputs.filter((o) => o.challenge.id === challenge.id);
    const parts = [theirs.length ? names(theirs) : null, variables.length ? `with your ${names(variables)}` : null].filter(Boolean);
    out.push({
      key: `c:${challenge.id}:${theirs.map((o) => o.id).join("+")}`, group: "Best start",
      title: `Find the models and data for ${theirs.length ? names(theirs) : challenge.label}`,
      detail: `I have a water problem · ${challenge.label}${parts.length ? ` · ${parts.join(" · ")}` : ""}`,
      go: challengeGo(challenge, theirs, variables),
    });
  }
  // 2. other outputs and challenges
  for (const o of outputs) {
    if (challenge && o.challenge.id === challenge.id) continue;
    out.push({ key: `o:${o.id}:${o.challenge.id}`, group: "Expected outputs", title: `Get a ${o.label}`,
               detail: `${o.question ? `“${o.question}” · ` : ""}${o.challenge.label}`, go: challengeGo(o.challenge, [o]) });
  }
  for (const c of challenges.slice(1)) {
    out.push({ key: `c:${c.id}`, group: "Water challenges", title: `Which models and data fit ${c.label}?`, detail: "I have a water problem", go: challengeGo(c) });
  }
  // 3. the data named: what it makes possible here
  if (named.length) {
    out.push({ key: `d:${named.map((v) => v.id).join("+")}`, group: "Your data",
               title: `I have ${names(named)} data: what can I do with it?`, detail: "I have data · choose your area, the open data is found for you",
               go: dataGo(named) });
  }
  // 4. a model: does it fit
  for (const s of software) {
    out.push({ key: `s:${s.id}`, group: "Models", title: `Does ${s.label} fit my study?`,
               detail: `I have a model${challenge ? ` · for ${challenge.label}` : ""}`, go: setupGo({ software: s.id }, challenge) });
  }
  for (const c of chains) {
    out.push({ key: `w:${c.id}`, group: "Models", title: `Check the workflow “${c.label}”`,
               detail: `standard workflow${c.challenges.length ? ` · ${names(c.challenges)}` : ""}`,
               go: setupGo({ reference_chain: c.id, methods: c.methods }, c.challenges[0] ?? challenge) });
  }
  // 5. always: the ontology, for anything else
  out.push({ key: "q", group: "Ontology", title: `Look up “${text.trim()}” in the ontology`, detail: "classes, properties, individuals and their definitions",
             go: { kind: "ontology", query: text.trim() } });
  return out;
}
