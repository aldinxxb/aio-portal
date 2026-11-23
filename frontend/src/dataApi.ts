// Entry 3, "Start from data": map layers of France and the open-data assessment.
import type { Chain, ChainRecommendation, Ref } from "./api";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export type LayerId = "basins" | "subbasins" | "regions" | "departments";

export type AreaFeature = {
  type: "Feature";
  properties: { id: string; name: string; bbox: [number, number, number, number] };
  geometry: { type: "MultiPolygon"; coordinates: number[][][][] };
};
export type AreaLayer = { layer: LayerId; title: string; note: string; features: AreaFeature[] };

export type Area = { layer: LayerId | "watersheds"; id: string; name: string; bbox: [number, number, number, number] };

export type Form = "series" | "map" | "points" | "static";
export type DataItem = {
  variable: string;
  source: "own" | "dataset";
  dataset: string | null;
  step: string | null;
  start: number | null;
  end: number | null;
  form: Form | null;
};

export type Role = "forcing" | "boundary" | "static" | "calibration" | "initial" | "unused";
export type DeclarableVariable = Ref & { role: Role; roles: Role[]; datasets: number; static: boolean };

export type Discovered = Ref & {
  url: string | null;
  publishers: Ref[];
  areas: Ref[];
  coverage: "full" | "partial";
  start: string | null;
  end: string | null;
  ongoing: boolean | null;
  temporal_nature: string | null;
  provenance: Ref[];
  measured: boolean;
  period: "full" | "partial" | "none" | null;
  variables: (Ref & { time_steps: string[]; grids: string[] })[];
};

export type Readiness = "hand" | "area" | "none";

export type Assessment = {
  area: Area | null;
  discovered: Discovered[];
  supply: { variables: number; datasets: number; full: number };
  roles: (Ref & { role: Role; roles: Role[]; roles_text: string[]; methods: number; workflows: number;
                 source: "own" | "dataset"; dataset: Ref | null; step: Ref | null; start: number | null;
                 end: number | null; form: Form | null })[];
  data_step: Ref | null;
  enables: (Ref & { workflows: number; hand: number; area: number; none: number; best: string | null;
                   outputs: (Ref & { level: Readiness })[] })[];
  objectives?: (Ref & { hand: number; area: number; workflows: number })[];
  outputs?: (Ref & { question: string | null; primary: boolean; hand: number; area: number; workflows: number;
                    variables: Ref[]; entity_match: boolean; suggested: boolean })[];
  workflows?: Omit<ChainRecommendation, "chains"> & { chains: (Chain & { readiness: Readiness })[] };
  next_datasets?: {
    dataset: Pick<Discovered, "id" | "label" | "url" | "publishers" | "coverage" | "start" | "end" | "ongoing"
                  | "temporal_nature" | "measured" | "period">;
    provides: (Ref & { time_steps: string[]; grids: string[] })[];
    finer: (Ref & { time_steps: string[]; grids: string[] })[];
    completes: string[];
    helps: string[];
  }[];
};

export type AssessBody = {
  area: Area | null;
  entity: string | null;
  data: DataItem[];
  challenge: string | null;
  objective: string | null;
  outputs: string[];
};

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init);
  if (!response.ok) throw new Error(`${path}: error ${response.status}`);
  return response.json() as Promise<T>;
}

const layers = new Map<LayerId, Promise<AreaLayer>>();
// Each layer is asked once per visit: the boundaries do not change.
export function getLayer(layer: LayerId): Promise<AreaLayer> {
  if (!layers.has(layer)) {
    const asked = call<AreaLayer>(`/geo/${layer}`);
    asked.catch(() => layers.delete(layer));
    layers.set(layer, asked);
  }
  return layers.get(layer)!;
}

export const getDeclarable = () => call<DeclarableVariable[]>("/opendata/variables");
export const getEntities = () => call<Ref[]>("/vocabulary/entity");

export const assess = (body: AssessBody) =>
  call<Assessment>("/opendata/assess", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

// The topographic watersheds (BD Topage) inside one study area, with that area's outline.
export type WatershedLayer = {
  title: string; note: string; source: string;
  area: AreaFeature;
  features: (AreaFeature & { properties: AreaFeature["properties"] & { centre: [number, number]; basin: string } })[];
};
const watersheds = new Map<string, Promise<WatershedLayer>>();
export function getWatersheds(layer: LayerId, id: string): Promise<WatershedLayer> {
  const key = `${layer}/${id}`;
  if (!watersheds.has(key)) {
    const asked = call<WatershedLayer>(`/geo/watersheds/${layer}/${encodeURIComponent(id)}`);
    asked.catch(() => watersheds.delete(key));
    watersheds.set(key, asked);
  }
  return watersheds.get(key)!;
}
