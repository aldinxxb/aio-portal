import type { ReachChallenge } from "../api";

export default function ChallengeCard({ item }: { item: ReachChallenge }) {
  const direct = item.counts.directly_applicable ?? 0;
  const needs = item.counts.needs_complementary_data ?? 0;
  const unknown = item.counts.inputs_not_recorded ?? 0;

  return (
    <article className={`challenge${direct > 0 ? " has-direct" : ""}`}>
      <h3 className="challenge-title">{item.label ?? item.id}</h3>
      <div className="tags">
        <span className="tag tag-direct">{direct} directly applicable</span>
        <span className="tag tag-complement">{needs} need more data</span>
        {unknown > 0 && <span className="tag tag-unknown">{unknown} inputs not recorded</span>}
      </div>
      {item.best.length > 0 && (
        <p className="result-note">
          Best matches:{" "}
          {item.best
            .map((m) => `${m.label ?? m.id}${m.score !== null ? ` (${Math.round(m.score * 100)}%)` : ""}`)
            .join(", ")}
        </p>
      )}
    </article>
  );
}