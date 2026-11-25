// The four starting points of the portal, named after the user's situation (shared by the
// app bar tabs and the start guide).
import type { ReactNode } from "react";
import type { Entry } from "./components/EntryCards";

const icon = {
  width: 22,
  height: 22,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

// Each starting point is named after the user's situation, not after the portal's internals.
export const CARDS: { id: Entry; title: string; text: string; icon: ReactNode }[] = [
  {
    id: "data",
    title: "I have data",
    text: "What can I do with it, here?",
    icon: (
      <svg {...icon}>
        <ellipse cx="12" cy="5" rx="8" ry="3" />
        <path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" />
        <path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
      </svg>
    ),
  },
  {
    id: "software",
    title: "I have a model",
    text: "Does my method or software fit my study?",
    icon: (
      <svg {...icon}>
        <circle cx="6" cy="12" r="2.5" />
        <circle cx="18" cy="6" r="2.5" />
        <circle cx="18" cy="18" r="2.5" />
        <path d="M8.2 10.8l7.6-3.6M8.2 13.2l7.6 3.6" />
      </svg>
    ),
  },
  {
    id: "challenge",
    title: "I have a water problem",
    text: "Which models and data fit it?",
    icon: (
      <svg {...icon}>
        <path d="M3 9c2.5-3 4.5-3 7 0s4.5 3 7 0 3-2 4-1M3 16c2.5-3 4.5-3 7 0s4.5 3 7 0 3-2 4-1" />
      </svg>
    ),
  },
  {
    id: "ontology",
    title: "Explore the ontology",
    text: "The knowledge model behind the portal",
    icon: (
      <svg {...icon}>
        <circle cx="12" cy="5" r="2.2" />
        <circle cx="5" cy="18" r="2.2" />
        <circle cx="19" cy="18" r="2.2" />
        <circle cx="12" cy="13" r="1.6" />
        <path d="M12 7.2v4.2M10.7 14.1l-4 2.7M13.3 14.1l4 2.7M7.2 18h9.6" />
      </svg>
    ),
  },
];
