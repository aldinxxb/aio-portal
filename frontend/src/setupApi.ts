// Modeling Approach entry: diagnose a modelling set-up and improve it.
// The backend keeps nothing between calls: this file holds the request shape, the
// calls, and the function that merges the patch of an accepted action.
import type { Ref } from "./api";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export type Setup = {
  software: string | null;
  methods: string[];
  roles: Record<string, string[]>;   // which job each method does
  reference_chain: string | null;
  // components removed ON PURPOSE (method -> the jobs it had): reported, never proposed again
  left_out?: Record<string, string[]>;
};

export type Context = {
  challenge: string | null;
  objective: string | null;
  intent: string | null;
  scenario: string | null;
  outputs: string[];                 // several expected outputs may be chosen
  output_step: string | null;        // the time step the results are wanted at
  entity: string | null;
};

export type DataItem = {
  variable: string;
  source: "own" | "dataset";
  dataset: string | null;
  step: string | null;
  resolution_m: number | null;
};

export type SetupRequest = { setup: Setup; context: Context; data: DataItem[] };

export const EMPTY_REQUEST: SetupRequest = {
  setup: { software: null, methods: [], roles: {}, reference_chain: null },
  context: { challenge: null, objective: null, intent: null, scenario: null, outputs: [], output_step: null, entity: null },
  data: [],
};

export type OptionStatus = "ok" | "needs_change" | "needs_combination" | "unavailable";
export type SetupOption = Ref & {
  status: OptionStatus;
  reason: string | null;
  count?: number;
  also?: Ref[];             // the other jobs a method can do
  receives?: Ref[];
  delivers?: Ref[];         // a method: what it gives in that job; a chain: the outputs it delivers
  methods?: Ref[];          // a reference chain: its essential methods
  optional_methods?: Ref[]; // ... and the optional ones (added later, in the diagnosis)
  software?: Ref[];
  same_software?: boolean;
  variables?: Ref[];        // an output: the variables behind it
  suggested?: boolean;
  question?: string | null; // an output: the question it answers, in plain words
  challenges?: Ref[];       // a reference chain: the water challenges it serves
  note?: string | null;
};
export type RoleGroup = { role: Ref; definition: string | null; options: SetupOption[] };

export type Nature = "forcing" | "boundary" | "static" | "initial";
// One recorded way of deriving a variable: from what (with the number of open datasets
// providing each input) and with which technique.
export type Derivation = { from: (Ref & { datasets: number })[]; how: string | null };
export type DataRow = Ref & {
  kind: "mandatory" | "optional" | "calibration" | "initial" | "parameter";
  status: "in_hand" | "available" | "derivable" | "needs_component" | "missing" | "unused" | "initial_state";
  nature: Nature;
  time_varying: boolean;
  used_by: Ref[];
  datasets: (Ref & { steps: string[]; measured: boolean; url: string | null })[];
  derivations: Derivation[];
  derived_from: Ref[];
  step: string | null;
  step_ref: Ref | null;
  source: "own" | "dataset" | null;
  dataset: (Ref & { url: string | null }) | null;   // the dataset chosen for it, if any
};

export type Issue = {
  key: string;
  code: string;
  severity: "blocking" | "warning" | "info";
  gain_hint: string;
  subject: string | null;
  message: string;
  detail: string;
};

export type Diagnosis = {
  study: {
    challenge: Ref | null; objective: Ref | null; intent: Ref | null; scenario: Ref | null;
    entity: Ref | null; driver: Ref | null; driver_assumed: boolean; output_step: Ref | null;
  };
  // what one method passes to the next; 'optional' = the receiver also runs without it
  links: { from: string; to: string; variables: Ref[]; optional: Ref[]; optional_only: boolean }[];   // what passes from one method to the next
  fit: { label: "fit" | "partly fit" | "poor fit"; score: number; message: string; blocking: number; warnings: number; infos: number };
  setup: {
    software: Ref | null;
    reference_chain: Ref | null;
    left_out: (Ref & { roles: Ref[] })[];   // components the user left out on purpose
    methods: (Ref & {
      roles: Ref[]; can_also: Ref[]; delivers: Ref[]; software: Ref[];
      runs_in: Ref | null;                       // the software it runs in here
      module: import("./api").Module | null;     // its module there: time step, resolution
      essential: boolean;                        // the study cannot do without it
    })[];   // upstream first
  };
  coverage: { primary: number; secondary: number; processes: Ref[]; roles_filled: Ref[] };
  best_template: (Ref & { slots: { role: Ref; mandatory: boolean; filled_by: Ref[] }[] }) | null;
  outputs: (Ref & {
    question: string | null;
    status: "delivered" | "needs_combination" | "unreachable";
    variables: Ref[];
    missing: Ref[];
    produced_by: string[];
    definition: string | null;
    forms: (Ref & { definition: string | null })[];
    // output <- variables <- the method of the set-up computing each one
    trace: (Ref & {
      computed_by: Ref[];
      gridded_by: Ref[];
      derivations: Derivation[];
      // not computed as such, but obtained from what the set-up computes
      derived: { from: Ref[]; how: string | null; computed_by: Ref[] } | null;
    })[];
    needs_grid: boolean;             // a map: needs a distributed or 2D/3D method
    drawable: boolean;
  })[];
  checks: { id: string; title: string; status: "ok" | "warn" | "fail"; message: string; detail: string }[];
  issues: Issue[];
  data: DataRow[];
  warnings: string[];
};

// What is missing, that an action supplies. Actions with the same target are alternatives.
export type Target = Ref & {
  type: "data" | "role" | "process" | "output" | "method" | "workflow" | "component";
  definition: string | null;
  nature?: Nature;                  // data: forcing, boundary condition, ...
  use?: DataRow["kind"];            // data: required input, calibration data, ...
};
// The variables a proposed method computes; 'use' says what a variable is needed for.
export type Contribution = { method: Ref; variables: (Ref & { use: string | null; new: boolean })[] };

export type Action = {
  id: string;
  target: Target;
  software: { same: boolean | null; software: Ref[]; current: Ref[]; text: string } | null;
  contributes: Contribution[];
  path: "more_data" | "finer_data" | "combine" | "replace";
  kind: string;
  group: "fix_first" | "recommended" | "optional";
  gain: string;
  effort: "low" | "medium" | "high";
  message: string;
  detail: string;
  patch: Record<string, unknown>;
  advice: boolean;
  standard_practice: boolean | null;
  exclusive_group: string | null;
  resolves: string[];
  effect: { fit_before: number; fit_after: number; label_after: string; blocking_before: number; blocking_after: number };
};

// One method of the set-up seen as a component that can be left out, with what is lost.
// In an integrated software each process is a module that can be switched off: a choice,
// not an error, but it has a price.
export type Component = Ref & {
  roles: Ref[];
  needed: boolean;                       // a mandatory part of the usual workflow
  verdict: "free" | "minor" | "costly";
  loses: {
    processes: (Ref & { main: boolean })[];   // no longer modelled (main = a main process of the challenge)
    variables: Ref[];                         // no longer computed
    outputs: Ref[];                           // expected outputs no longer delivered
    // a method that received a variable from this one and now needs it another way
    downstream: { method: Ref; variable: Ref; required: boolean; nature: Nature; then: DataRow["status"] }[];
    blocking: string[];                       // new blocking issues
  };
  effect: { fit_before: number; fit_after: number; blocking_after: number };
  same_software: Ref[];                  // other methods of the same software for the same job
  // ... each one tried: what the fit becomes if it replaces this method
  alternatives: (Ref & {
    roles: Ref[];
    software: Ref[];
    fit_after: number;
    blocking_after: number;
    outputs_lost: string[];
    same_software: boolean;
    module: import("./api").Module | null;
    patch: Record<string, unknown>;
  })[];
  patch: Record<string, unknown>;
};

export type Improvement = {
  diagnosis: Diagnosis;
  actions: Action[];
  more_available: number;
  components: Component[];
};

// The same question always has the same answer (until the ontology changes), so every
// answer is kept: going back, or picking the same thing again, costs no call at all.
const kept = new Map<string, Promise<unknown>>();
const KEEP_AT_MOST = 300;

function post<T>(path: string, body: unknown): Promise<T> {
  const text = JSON.stringify(body);
  const key = `${path}|${text}`;
  const found = kept.get(key);
  if (found) return found as Promise<T>;
  const answer = fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: text,
  }).then(async (response) => {
    if (!response.ok) {
      const detail = await response.json().catch(() => null);
      const why = Array.isArray(detail?.detail) ? detail.detail.join("; ") : `error ${response.status}`;
      throw new Error(`${path}: ${why}`);
    }
    return response.json() as Promise<T>;
  });
  if (kept.size >= KEEP_AT_MOST) kept.delete(kept.keys().next().value as string);
  kept.set(key, answer);
  answer.catch(() => kept.delete(key));          // a failed call is asked again next time
  return answer;
}

// Only the parts of the request a step looks at are sent: the answer can then be reused
// when something else changes (the list of objectives does not depend on the data).
const NEEDS: Record<string, (r: SetupRequest) => unknown> = {
  software: () => ({}),
  intent: () => ({}),
  scenario: () => ({}),
  entity: () => ({}),
  methods: (r) => ({ setup: { software: r.setup.software } }),
  reference_chain: (r) => ({ setup: { software: r.setup.software } }),
  challenge: (r) => ({ setup: r.setup }),
  objective: (r) => ({ setup: r.setup }),
  output: (r) => ({ setup: r.setup, context: { challenge: r.context.challenge } }),
};

export const setupOptions = <T,>(step: string, request: SetupRequest) =>
  post<T>("/setup/options", { step, request: NEEDS[step] ? NEEDS[step](request) : request });

export const improveSetup = (request: SetupRequest) => post<Improvement>("/setup/improve", request);

// Merge the patch of an accepted action into the request (the backend does the same
// when it measures the effect of an action).
export function applyPatch(request: SetupRequest, patch: Record<string, unknown>): SetupRequest {
  const next: SetupRequest = {
    setup: {
      ...request.setup,
      methods: [...request.setup.methods],
      roles: { ...request.setup.roles },
      left_out: { ...(request.setup.left_out ?? {}) },
    },
    context: request.context,
    data: [...request.data],
  };
  for (const [key, value] of Object.entries(patch)) {
    if (key === "data+") {
      const items = value as DataItem[];
      const variables = new Set(items.map((d) => d.variable));
      next.data = [...next.data.filter((d) => !variables.has(d.variable)), ...items];
    } else if (key === "setup.methods+") {
      for (const m of value as string[]) if (!next.setup.methods.includes(m)) next.setup.methods.push(m);
    } else if (key === "setup.methods-") {
      const gone = value as string[];
      next.setup.methods = next.setup.methods.filter((m) => !gone.includes(m));
      for (const m of gone) delete next.setup.roles[m];
    } else if (key === "setup.roles+") {
      Object.assign(next.setup.roles, value as Record<string, string[]>);
    } else if (key === "setup.left_out+") {
      Object.assign(next.setup.left_out!, value as Record<string, string[]>);
    } else if (key === "setup.left_out-") {
      for (const m of value as string[]) delete next.setup.left_out![m];
    } else if (key === "setup") {
      next.setup = { ...next.setup, ...(value as Partial<Setup>) };
    }
  }
  return next;
}
