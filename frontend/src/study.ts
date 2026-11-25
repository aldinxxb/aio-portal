// One study, carried from one entry to another: the challenge, the objective, the expected
// outputs, the data in hand and, when known, the study area. Each entry describes the same study
// in its own words; these builders turn it into the state of another entry (see StudyBridge).

import type { Ref } from "./api";
import type { DataState } from "./components/DataEntry";
import type { SetupState } from "./components/SetupEntry";
import type { LayerId } from "./dataApi";
import { EMPTY_REQUEST } from "./setupApi";
import type { Go } from "./searchIndex";

export type Study = {
  challenge: Ref | null;
  objective: Ref | null;
  outputs: Ref[];
  data: { variable: Ref; step: string | null }[];
  area?: { layer: LayerId; id: string; name: string; sheds?: string[] } | null;
};

const label = (r: Ref) => r.label ?? r.id;

export function studyLine(study: Study): string {
  return [
    study.area?.name ? `📍 ${study.area.name}` : "",
    study.challenge ? label(study.challenge) : "",
    study.objective ? label(study.objective) : "",
    study.outputs.map(label).join(", "),
    study.data.length ? `${study.data.length} data in hand` : "no data of your own",
  ].filter(Boolean).join(" · ");
}

// "I have a water problem": its ranked results at once (the answers are all given)
export function toChallenge(study: Study): Go {
  const named = [study.challenge, study.objective, ...study.outputs, ...study.data.map((d) => d.variable)].filter(Boolean) as Ref[];
  return {
    kind: "results",
    state: {
      answers: {
        challenge: study.challenge?.id,
        objective: study.objective?.id,
        outputs: study.outputs.map((o) => o.id),
        available_variables: study.data.map((d) => d.variable.id),
        data_time_step: study.data.find((d) => d.step)?.step ?? undefined,
      },
      labels: Object.fromEntries(named.map((r) => [r.id, label(r)])),
    },
  };
}

// "I have data": the workflows of the area when it is known, else the map with the goal filled in
export function toData(study: Study): Go {
  const state: DataState = {
    page: study.area ? 3 : 0,
    layer: study.area?.layer,
    area: study.area?.id,
    sheds: study.area?.sheds,
    challenge: study.challenge?.id ?? null,
    objective: study.objective?.id ?? null,
    outputs: study.outputs.map((o) => o.id),
    data: study.data.map((d) => ({ variable: d.variable.id, source: "own", dataset: null, step: d.step, start: null, end: null, form: null })),
  };
  return { kind: "data", state };
}

// "I have a model": the study and the data filled in; the user describes the set-up
export function toSetup(study: Study): Go {
  const state: SetupState = {
    step: 0,
    request: {
      ...EMPTY_REQUEST,
      context: { ...EMPTY_REQUEST.context, challenge: study.challenge?.id ?? null, objective: study.objective?.id ?? null,
                 outputs: study.outputs.map((o) => o.id) },
      data: study.data.map((d) => ({ variable: d.variable.id, source: "own" as const, dataset: null, step: d.step, resolution_m: null })),
    },
  };
  return { kind: "setup", state };
}
