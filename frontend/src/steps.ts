import type { Draft } from "./api";

// One wizard step. The wizard reads this list and never hard-codes a question.
export type Step = {
  id: string;           // must match a key of STEPS in backend/app/options.py
  title: string;        // short name shown in the progress bar
  question: string;     // text shown to the user
  multiple: boolean;    // can the user pick several options?
  field: keyof Draft;   // which Draft field the answer is stored in
};

export const CHALLENGE_STEPS: Step[] = [
  {
    id: "challenge",
    title: "Challenge",
    question: "What is your water challenge?",
    multiple: false,
    field: "challenge",
  },
  {
    id: "process",
    title: "Processes",
    question: "Which hydrological processes matter to you?",
    multiple: true,
    field: "processes",
  },
  {
    id: "variable",
    title: "Data",
    question: "Which data do you already have?",
    multiple: true,
    field: "available_variables",
  },
  {
    id: "scale",
    title: "Scale",
    question: "At which spatial scale do you work? (optional)",
    multiple: true,
    field: "scales",
  },
  {
    id: "timestep",
    title: "Time step",
    question: "Which time step do you need? (optional)",
    multiple: true,
    field: "time_steps",
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