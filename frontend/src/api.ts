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
};

export type Recommendation = {
  urr: { processes: { values: string[]; source: "stated" | "derived" } };
  counts: Partial<Record<Status, number>>;   filtered_out: number;
  results: Result[];
};

export type RecommendRequest = {
  challenge: string;
  processes: string[];
  available_variables: string[];
  scales?: string[];
  time_steps?: string[];
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, options);
  if (!response.ok) {
    throw new Error(`The API answered ${response.status} for ${path}`);
  }
  return response.json() as Promise<T>;
}

export const getChallenges = () => request<Item[]>("/challenges");

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
  provides: Ref[];   // the requested variables this dataset provides
};

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