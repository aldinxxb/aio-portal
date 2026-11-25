import { CARDS } from "../entries";

export type Entry = "challenge" | "software" | "data" | "ontology";

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