import { useState } from "react";
import { checkMethod, type MethodCheck, type MethodProfile, type Ref, type Status } from "../api";

type ListKey = "challenges" | "processes" | "outputs" | "software" | "scales" | "time_steps";

// Facts shown as plain lines. (Inputs are handled separately, as tick boxes.)
const SECTIONS: { key: ListKey; title: string }[] = [
  { key: "challenges", title: "Addresses challenges" },
  { key: "processes", title: "Models processes" },
  { key: "outputs", title: "Produces" },
  { key: "software", title: "Runs in" },
  { key: "scales", title: "Application scales" },
  { key: "time_steps", title: "Typical time steps" },
];

const BADGE: Record<Status, { css: string; text: string }> = {
  directly_applicable: { css: "is-direct", text: "Ready to run" },
  needs_complementary_data: { css: "is-complement", text: "Missing data" },
  inputs_not_recorded: { css: "is-unknown", text: "Inputs not recorded" },
};

const names = (items: Ref[]) => items.map((i) => i.label ?? i.id).join(", ");

export default function MethodCard({ profile }: { profile: MethodProfile }) {
  const [have, setHave] = useState<string[]>([]);       // ids of the data the user ticked
  const [check, setCheck] = useState<MethodCheck | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggle(id: string) {
    const next = have.includes(id) ? have.filter((h) => h !== id) : [...have, id];
    setHave(next);
    try {
      setCheck(await checkMethod(profile.id, next));   // the backend decides the verdict
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }

  function tickBox(input: Ref, tag: string) {
    return (
      <label key={input.id} className="tick">
        <input type="checkbox" checked={have.includes(input.id)} onChange={() => toggle(input.id)} />{" "}
        {input.label ?? input.id} <span className="muted">({tag})</span>
      </label>
    );
  }

  return (
    <details className="method">
      <summary>{profile.label ?? profile.id}</summary>

      <div className="method-body">
        {SECTIONS.map(({ key, title }) => (
          <div key={key} className="row">
            <span className="muted">{title}: </span>
            {profile[key].length ? names(profile[key]) : <em>not recorded</em>}
          </div>
        ))}

        <div style={{ marginTop: 10 }}>
          <strong>Which of these data do you already use?</strong>
          {profile.mandatory_inputs.length === 0 && profile.optional_inputs.length === 0 && (
            <div>
              <em>The ontology records no inputs for this method.</em>
            </div>
          )}
          {profile.mandatory_inputs.map((i) => tickBox(i, "required"))}
          {profile.optional_inputs.map((i) => tickBox(i, "optional"))}
        </div>

        {error && <p className="error">{error}</p>}

        {check && (
          <div className={`verdict ${BADGE[check.status].css}`}>
            <strong>{BADGE[check.status].text}</strong>
            {check.coverage !== null && <> · {Math.round(check.coverage * 100)}% of required inputs</>}
            {check.inputs_missing.length > 0 && <div>Still needed: {names(check.inputs_missing)}</div>}
            {check.optional_unused.length > 0 && (
              <div>Would improve the result: {names(check.optional_unused)}</div>
            )}
          </div>
        )}
      </div>
    </details>
  );
}