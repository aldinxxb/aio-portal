import type { ReactNode } from "react";

export type Entry = "challenge" | "software" | "data" | "ontology";

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

const CARDS: { id: Entry; title: string; text: string; icon: ReactNode }[] = [
  {
    id: "data",
    title: "Start from Data",
    text: "I have data, what can I do?",
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
    title: "Start from Modeling Approach",
    text: "I want to use a method or software, what do I need?",
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
    title: "Start from Water Challenge",
    text: "What models and data fit this issue?",
    icon: (
      <svg {...icon}>
        <path d="M3 9c2.5-3 4.5-3 7 0s4.5 3 7 0 3-2 4-1M3 16c2.5-3 4.5-3 7 0s4.5 3 7 0 3-2 4-1" />
      </svg>
    ),
  },
  {
    id: "ontology",
    title: "AIO Ontology",
    text: "Browse the knowledge model behind the portal",
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

type Props = {
  selected: Entry | null;            // which card is dark
  onChoose: (entry: Entry) => void;
};

export default function EntryCards({ selected, onChoose }: Props) {
  return (
    <div className="entries">
      {CARDS.map((card) => (
        <button
          key={card.id}
          className={`entry${selected === card.id ? " active" : ""}`}
          aria-current={selected === card.id ? "page" : undefined}
          title={card.text}
          onClick={() => onChoose(card.id)}
        >
          <span className="entry-icon">{card.icon}</span>
          <span>
            <span className="entry-title">{card.title}</span>
            <span className="entry-text">{card.text}</span>
          </span>
        </button>
      ))}
    </div>
  );
}