import type { Draft } from "./api";

// One wizard step. The wizard reads this list and never hard-codes a question.
export type Step = {
  id: string;           // must match a key of STEPS in backend/app/options.py
  title: string;        // short name shown in the progress bar
  question: string;     // text shown to the user
  multiple: boolean;    // can the user pick several options?
  field: keyof Draft;   // which Draft field the answer is stored in
  optional?: boolean;   // single-choice step the user may skip (multiple steps always can)
  countOf?: string;     // what the number next to an option counts (default: "method(s)")
  relatedTitle?: string; // name of the "related" list of an option (outputs: "Variables")
  skipWhen?: (draft: Draft) => boolean;   // a step not asked when this holds
  skipNote?: string;                      // why it was not asked, shown in its place
  sub?: string;         // a few words under the title in the step bar
  refine?: boolean;     // not asked in the questions: added later from the results ("Refine")
};

const LEFT = "method(s) still possible with this choice";

export const CHALLENGE_STEPS: Step[] = [
  {
    id: "challenge",
    title: "Challenge",
    sub: "flood, drought…",
    question: "What is your water challenge?",
    multiple: false,
    field: "challenge",
  },
  // ---- the problem definition: what do you want to know? ----
  {
    id: "objective",
    title: "Goal",
    sub: "simulate, forecast…",
    question: "What is the goal of your study? (optional)",
    multiple: false,
    field: "objective",
    optional: true,
    countOf: LEFT,
  },
  {
    id: "driver",
    title: "Drivers",
    refine: true,
    question: "Which drivers do you want to study? (optional)",
    multiple: true,
    field: "drivers",
    countOf: LEFT,
  },
  {
    id: "output",
    title: "Outputs",
    sub: "the results you need",
    question: "Which results do you expect? (optional)",
    multiple: true,
    field: "outputs",
    countOf: LEFT,
    relatedTitle: "Variables",
  },
  // ---- the technical side: processes, data, scale, time step ----
  {
    id: "process",
    title: "Processes",
    refine: true,
    question: "Which hydrological processes matter to you?",
    multiple: true,
    field: "processes",
    // expected outputs chosen: the processes are those of the workflows delivering them
    skipWhen: (draft) => (draft.outputs?.length ?? 0) > 0,
    skipNote: "set by your expected outputs",
  },
  {
    id: "variable",
    title: "Your data",
    sub: "what you already have",
    question: "Which data do you already have?",
    multiple: true,
    field: "available_variables",
  },
  {
    id: "datastep",
    title: "Data step",
    refine: true,
    question: "At which time step is your data? (optional)",
    multiple: false,
    field: "data_time_step",
    optional: true,
    countOf: "method(s) that can use data at this step as it is",
  },
  {
    id: "scale",
    title: "Scale",
    refine: true,
    question: "At which spatial scale do you work? (optional)",
    multiple: true,
    field: "scales",
  },
  {
    id: "timestep",
    title: "Time step",
    refine: true,
    question: "At which time step do you need the results? (optional)",
    multiple: true,
    field: "time_steps",
    countOf: "method(s) running at this step or finer",
  },
];
export const SOFTWARE_STEPS: Step[] = [
  {
    id: "software",
    title: "Software",
    question: "Which software do you use?",
    multiple: false,
    field: "software",
  },
  {
    id: "method",
    title: "Methods",
    question: "Which methods are you interested in?",
    multiple: true,
    field: "methods",
  },
];

export const DATA_STEPS: Step[] = [
  {
    id: "data",
    title: "Data",
    question: "Which data do you have?",
    multiple: true,
    field: "available_variables",
  },
];