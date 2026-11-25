const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export type Item = { id: string; label: string | null };

export type Status =
  | "directly_applicable"
  | "needs_complementary_data"
  | "inputs_not_recorded";

export type InputRef = { id: string; label: string };

export type Result = {
  id: string;
  label: string | null;
  status: Status;
  score: number | null;
  input_coverage: number | null;
  process_match: number;
  processes: string[];
  inputs_available: InputRef[];
  inputs_missing: InputRef[];
  explanation: string;
  // what the ontology records about the method (Lesson 41)
  physical_parameters: Ref[];
  calibration_parameters: Ref[];
  outputs: Ref[];               // the variables it produces
  software: Ref[];              // the software that implements it
  time_step: TimeStepInfo;      // steps it runs at, and how they fit the user's (0.8.0)
  // two separate views of a result: does the method suit the study, can its data be gathered
  roles: RoleView[];            // the job(s) the method can do in a model
  inputs: MethodInput[];        // each input with its kind and where it can come from
  compatibility: { score: number; process_match: number; rules_passed: number; rules_failed: number };
  availability: {
    score: number | null;       // share of the required inputs the user already has
    with_open_data: number | null;
    have: number;
    open_data: number;
    missing: number;
    needs_disaggregation: boolean;
  };
  // only when the requirement rules were applied (the user defined a problem):
  base_score?: number | null;   // the score before the soft rules
  rule_adjustment?: number;     // what the soft rules added or removed
  reasons?: Reason[];           // one line per rule: passed, failed or unknown
};

// forcing: from outside the water system · boundary: a flow or level entering the model at
// its limits · static: fixed description of the site · initial: initial state
export type InputKind = "forcing" | "boundary" | "static" | "initial";
export type MethodInput = {
  id: string;
  label: string | null;
  kind: InputKind;
  state: "have" | "open_data" | "missing" | "initial";
  required: boolean;
};

// One job a method can do, with what it receives and gives in that job
// (Linear Reservoir: runoff transform, or baseflow).
export type RoleView = {
  id: string;
  label: string | null;
  definition: string | null;
  receives: { id: string; label: string | null }[];
  usually_receives: { id: string; label: string | null }[];
  delivers: { id: string; label: string | null }[];
};

// ---- Requirement rules (Lesson 40) ----

// A rule that one of the user's choices implies (e.g. Forecasting -> continuous simulation).
export type Requirement = {
  id: string;
  kind: "method" | "data" | "presentation";
  label: string | null;
  rationale: string | null;
  strength: "hard" | "soft" | "none";
  weight: number;
  because: string[];            // the chosen values that caused it
};

// How one method did on one rule.
export type Reason = {
  requirement: string;
  label: string | null;
  strength: "hard" | "soft" | "none";
  status: "pass" | "fail" | "unknown";
  detail: string;
  effect: number;               // change of the score (0 for hard rules)
  rationale: string | null;
};

export type ExcludedMethod = { id: string; label: string | null; reasons: Reason[] };

// An output the user expects, with the variables a method must produce to deliver it.
// An output the user expects: the question it answers, its form, the variables behind it
// (each with the recommended methods computing it) and the water entities it concerns.
export type ExpectedOutput = {
  id: string;
  label: string | null;
  question: string | null;
  forms: Ref[];                                   // time series, map, indicator
  entities: Ref[];
  variables: (Ref & { computed_by: Ref[]; count: number; derivable_from: Ref[] })[];
};

// How a method is implemented in one software: module, time step, spatial resolution.
export type Module = {
  id: string;
  name: string | null;
  time_step: string | null;
  time_step_classes: string[];
  spatial_unit: string | null;
  resolution: string | null;
  software: Ref;
};

export type Recommendation = {
  urr: { processes: { values: string[]; source: "stated" | "derived" } };
  expected_outputs: ExpectedOutput[];
  // for information: the water entities and processes concerned by the problem
  related_entities: (Ref & { outputs: string[] })[];
  related_processes: { values: Ref[]; source: "stated" | "outputs" | "derived"; primary: string[] };
  counts: Partial<Record<Status, number>>;   filtered_out: number;
  rules_applied: boolean;
  requirements: Requirement[];
  excluded_by_rules: number;
  excluded_methods: ExcludedMethod[];
  results: Result[];
};

export type RecommendRequest = {
  challenge: string;
  processes: string[];
  available_variables: string[];
  scales?: string[];
  time_steps?: string[];
  // the problem definition (all optional)
  objective?: string;
  entity?: string;
  drivers?: string[];
  outputs?: string[];
  data_time_step?: string;      // time step of the user's data
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, options);
  if (!response.ok) {
    throw new Error(`The API answered ${response.status} for ${path}`);
  }
  return response.json() as Promise<T>;
}

export const getChallenges = () => request<Item[]>("/challenges");

// the expected outputs of a challenge, with the plain question each one answers
export type ChallengeOutput = { id: string; label: string; question: string | null; primary: boolean };
export const getChallengeOutputs = (challengeId: string) =>
  request<ChallengeOutput[]>(`/challenges/${encodeURIComponent(challengeId)}/outputs`);

export const getProcesses = (challengeId: string) =>
  request<Item[]>(`/challenges/${encodeURIComponent(challengeId)}/processes`);

export const getVariables = () => request<Item[]>("/variables");

export const recommend = (body: RecommendRequest) =>
  request<Recommendation>("/recommend", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  // ---- Wizard (Stage 2) ----

// One button in a wizard step, exactly as the backend sends it.
export type Option = {
  id: string;
  label: string;
  count: number;
  enabled: boolean;
  reason: string | null; // why the option is greyed out (null when enabled)
  hint: string | null;   // a short sentence shown under the option (null = nothing)
  suggested: boolean;    // does the ontology propose this option first?
  related: Ref[];        // concepts tied to the option (for an output: its variables)
};

// The answers given so far. Every field is optional because the wizard fills them one by one.
export type Draft = {
  challenge?: string;
  processes?: string[];
  available_variables?: string[];
  scales?: string[];
  time_steps?: string[];
  software?: string;
  methods?: string[];
  // the problem definition (Lesson 39)
  objective?: string;
  entity?: string;
  drivers?: string[];
  outputs?: string[];
  data_time_step?: string;      // time step of the user's data (0.8.0)
};

export async function getOptions(step: string, draft: Draft): Promise<Option[]> {
  const response = await fetch(`${API_URL}/options/${step}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(draft),
  });
  if (!response.ok) {
    throw new Error(`Options for step "${step}" failed (${response.status})`);
  }
  const data = await response.json();
  return data.options;
}
// ---- Method detail (Entry 2) ----

export type Ref = { id: string; label: string | null };

export type MethodProfile = {
  id: string;
  label: string | null;
  challenges: Ref[];
  processes: Ref[];
  mandatory_inputs: Ref[];
  optional_inputs: Ref[];
  outputs: Ref[];
  software: Ref[];
  scales: Ref[];
  time_steps: Ref[];
};

export async function getMethod(id: string): Promise<MethodProfile> {
  const response = await fetch(`${API_URL}/methods/${encodeURIComponent(id)}`);
  if (!response.ok) {
    throw new Error(`Method "${id}" failed (${response.status})`);
  }
  return response.json();
}
export type MethodCheck = {
  status: Status;
  coverage: number | null;
  inputs_available: Ref[];
  inputs_missing: Ref[];
  optional_used: Ref[];
  optional_unused: Ref[];
};

export async function checkMethod(id: string, available: string[]): Promise<MethodCheck> {
  const response = await fetch(`${API_URL}/methods/${encodeURIComponent(id)}/check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ available_variables: available }),
  });
  if (!response.ok) {
    throw new Error(`Check for "${id}" failed (${response.status})`);
  }
  return response.json();
}
// ---- Entry 3: what can my data do? ----

export type ReachChallenge = {
  id: string;
  label: string | null;
  counts: Partial<Record<Status, number>>;
  best: { id: string; label: string | null; score: number | null }[];
  // every method usable right now, with what it produces and where it runs
  direct: { id: string; label: string | null; score: number | null; outputs: Ref[]; software: Ref[] }[];
  nearly: { id: string; label: string | null; missing: Ref }[];   // one input away
  next_data: (Ref & { unlocks: number; open_data: boolean })[];   // what to add next
  workflows: {
    id: string;
    label: string;
    status: "runnable" | "check";
    reasons: string[];
    software: Ref[];
    methods: Ref[];
    inputs: (Ref & { kind: "input" | "parameter"; state: DataState })[];
  }[];
};

export async function reach(available: string[]): Promise<ReachChallenge[]> {
  const response = await fetch(`${API_URL}/reach`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ available_variables: available }),
  });
  if (!response.ok) {
    throw new Error(`Reach failed (${response.status})`);
  }
  const data = await response.json();
  return data.challenges;
}

// ---- Open data layer ----

export type Dataset = {
  id: string;
  label: string | null;
  publishers: Ref[];
  coverage: Ref[];
  url: string | null;
  start: string | null;            // period covered, e.g. "1940-01-01"
  end: string | null;
  ongoing: boolean | null;         // still updated?
  temporal_nature: string | null;  // e.g. "time series record"
  provides: ProvidedVariable[];    // the requested variables this dataset provides
  matched_by?: "dataset" | "variable";   // search only: found by its name or by a variable
};

// A variable inside a dataset, with the resolutions it comes at.
export type ProvidedVariable = Ref & {
  time_steps: string[];   // e.g. ["1 hour"]
  grids: string[];        // e.g. ["0.25°"]
};

// ---- Dataset search by variable name (Lesson 42) ----

// A variable that can be derived from other data: from what, and with which technique.
export type DerivedVariable = Ref & {
  datasets: number;                // open datasets providing it directly
  derivations: { from: (Ref & { datasets: number })[]; how: string | null }[];
};
export type DatasetSearch = { query: string; variables: Ref[]; datasets: Dataset[]; derived: DerivedVariable[] };
export type DatasetVariable = Ref & { count: number };   // count = number of datasets

export const searchDatasets = (text: string) =>
  request<DatasetSearch>(`/datasets/search?q=${encodeURIComponent(text)}`);

export const getDatasetVariables = () => request<DatasetVariable[]>("/datasets/variables");

export async function getDatasets(variables: string[]): Promise<Dataset[]> {
  const response = await fetch(`${API_URL}/datasets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ variables }),
  });
  if (!response.ok) {
    throw new Error(`Datasets failed (${response.status})`);
  }
  const data = await response.json();
  return data.datasets;
}

// ---- Workflow & knowledge graph ----

export type GraphNode = {
  id: string;
  kind: "challenge" | "process" | "method" | "software" | "variable" | "dataset";
  label: string;
  have: boolean | null;   // only for variables: do you have this data?
};
export type GraphEdge = { source: string; target: string };
export type Workflow = { nodes: GraphNode[]; edges: GraphEdge[] };

export async function getWorkflow(
  body: RecommendRequest & { methods?: string[] }
): Promise<Workflow> {
  const response = await fetch(`${API_URL}/workflow`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`Workflow failed (${response.status})`);
  }
  return response.json();
}
// ---- Ontology 0.8.0: time steps and method chains ----

// What the backend says about the time step of one method.
export type TimeStepInfo = {
  supports: Ref[];                 // every step the method can run at, finest first
  typical: Ref[];                  // the usual one(s)
  needs_disaggregation: boolean;   // the data is coarser than every step the method runs at
  notes: string[];
};

export type DataState = "internal" | "have" | "open_data" | "missing";
export type StatedRef = Ref & { state: DataState };

// What appears when a step of a chain is opened.
export type MethodDetail = {
  mandatory_inputs: StatedRef[];
  optional_inputs: Ref[];
  initial_conditions: Ref[];
  physical_parameters: StatedRef[];
  calibration_parameters: Ref[];
  outputs: Ref[];
  supports_time_steps: Ref[];
  typical_time_steps: Ref[];
  temporal_modes: Ref[];
  software: Ref[];
};

export type ChainStep = {
  order: number;
  method: Ref;
  roles: Ref[];                    // the job(s) the method does in the chain
  software: Ref | null;
  issue: string | null;            // why this step is a problem (null = fine)
  alternatives: (Ref & { same_software: boolean })[];   // methods that could replace it
  detail: MethodDetail;
  module: Module | null;           // how it runs in its software (time step, resolution)
  essential: boolean;
};

// A component of a standard workflow left out at first (its effect can be neglected).
export type OptionalStep = {
  method: Ref;
  roles: Ref[];
  software: Ref | null;
  module: Module | null;
  adds_processes: Ref[];
  adds_variables: Ref[];
};

export type Chain = {
  id: string;
  label: string;
  kind: "reference" | "generated"; // curated standard practice, or built by the portal
  optional_steps: OptionalStep[];  // components that can be added to refine it
  note: string | null;
  template: Ref | null;
  delivers: Ref[];
  coupling: Ref | null;
  status: "runnable" | "check";
  reasons: string[];
  score: number | null;
  coverage: number | null;         // share of the primary processes of the challenge
  covers: Ref[];
  software: (Ref & { open: boolean; free: boolean })[];
  all_open: boolean;
  all_free: boolean;
  steps: ChainStep[];
  // what you must bring, each with its nature (forcing, boundary condition, static description)
  inputs: (Ref & { kind: "input" | "parameter"; state: DataState; nature?: "forcing" | "boundary" | "static" })[];
  initial_conditions: Ref[];
  calibration: { needed: boolean; ok: boolean; against: Ref[] };
  temporal_modes: Ref[];
};

export type ChainRecommendation = {
  note: string | null;
  templates: { id: string; label: string | null; definition: string | null }[];
  chains: Chain[];
};

export type Licence = "open" | "free" | null;

export const getChains = (body: RecommendRequest & { licence?: Licence; software?: string | null }) =>
  request<ChainRecommendation>("/chains", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

// ---- Modeling Approach entry: what a method can be combined with ----

export type Neighbour = Ref & { roles: Ref[]; same_software: boolean; shared_software: Ref[] };

export type InputSource = Ref & {
  kind: "mandatory" | "optional" | "parameter" | "initial";
  have: boolean;
  datasets: (Ref & { steps: Ref[]; fine_enough: boolean })[];
  derived_from: Ref[];
  producers: Neighbour[];          // methods whose output can provide it
};

export type Combination = Ref & {
  roles: Ref[];
  complete_model: boolean;
  supports_time_steps: Ref[];
  typical_time_steps: Ref[];
  alone: { status: "runnable" | "check"; reasons: string[] };
  fed_by: Neighbour[];
  feeds: Neighbour[];
  alternatives: Neighbour[];
  chains: (Ref & { methods: Ref[]; software: Ref[]; same_software: boolean; template: Ref | null })[];
  inputs: InputSource[];
};

export const combineMethod = (id: string, available: string[], software?: string) =>
  request<Combination>(`/methods/${encodeURIComponent(id)}/combine`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ available_variables: available, software }),
  });

// ---- Open data layer: what the search box can propose ----

export type DatasetSuggestions = {
  derived: Ref[];              // parameters that can be derived from other data
  variables: DatasetVariable[];
  datasets: (Ref & { count: number })[];   // count = number of variables
};

export const getDatasetSuggestions = () => request<DatasetSuggestions>("/datasets/suggestions");
