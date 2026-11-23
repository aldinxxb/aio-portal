import { useState } from "react";
import {
  checkMethod,
  combineMethod,
  type Combination,
  type InputSource,
  type MethodCheck,
  type MethodProfile,
  type Neighbour,
  type Ref,
  type Status,
} from "../api";

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

const KIND: Record<InputSource["kind"], string> = {
  mandatory: "required",
  optional: "optional",
  parameter: "parameter",
  initial: "initial state",
};

const name = (item: Ref) => item.label ?? item.id;
const names = (items: Ref[]) => items.map(name).join(", ");

// Methods that can be placed before or after this one. Those available in the
// software the user chose are marked.
function Neighbours({ items, empty }: { items: Neighbour[]; empty: string }) {
  if (items.length === 0) return <p className="muted">{empty}</p>;
  return (
    <div className="pills">
      {items.map((n) => (
        <span
          key={n.id}
          className={`pill${n.same_software ? " pill-hit" : ""}`}
          title={`${names(n.roles)}${n.shared_software.length ? ` · shared software: ${names(n.shared_software)}` : ""}`}
        >
          {n.same_software && "● "}
          {name(n)}
        </span>
      ))}
    </div>
  );
}

// Where one input can come from: the user, open data fine enough, a derivation, another method.
function Source({ input }: { input: InputSource }) {
  const fine = input.datasets.filter((d) => d.fine_enough);
  const coarse = input.datasets.filter((d) => !d.fine_enough);
  const ways: string[] = [];
  if (fine.length) ways.push(`open data: ${names(fine)}`);
  if (coarse.length) ways.push(`too coarse for this method: ${names(coarse)}`);
  if (input.derived_from.length) ways.push(`derived from ${names(input.derived_from)}`);
  if (input.producers.length) ways.push(`computed by ${names(input.producers.slice(0, 4))}`);
  if (input.kind === "initial") ways.push("warm-up run or observed snapshot");

  return (
    <div className="line">
      <span className={`pill${input.have ? " pill-hit" : ""}`}>
        {input.have && "✓ "}
        {name(input)}
      </span>{" "}
      <span className="muted">({KIND[input.kind]})</span>{" "}
      {input.have ? "you have it" : ways.length ? ways.join(" · ") : <span className="reason-fail">no source recorded</span>}
    </div>
  );
}

type Props = {
  profile: MethodProfile;
  software?: string;   // the software chosen in the wizard: its methods are marked
};

export default function MethodCard({ profile, software }: Props) {
  const [have, setHave] = useState<string[]>([]);       // ids of the data the user ticked
  const [check, setCheck] = useState<MethodCheck | null>(null);
  const [combo, setCombo] = useState<Combination | null>(null);
  const [error, setError] = useState<string | null>(null);

  // What the method can be combined with, given the data ticked so far.
  async function loadCombination(available: string[]) {
    try {
      setCombo(await combineMethod(profile.id, available, software));
    } catch (e) {
      setError(String(e));
    }
  }

  async function toggle(id: string) {
    const next = have.includes(id) ? have.filter((h) => h !== id) : [...have, id];
    setHave(next);
    try {
      setCheck(await checkMethod(profile.id, next));   // the backend decides the verdict
      setError(null);
    } catch (e) {
      setError(String(e));
    }
    loadCombination(next);
  }

  function tickBox(input: Ref, tag: string) {
    return (
      <label key={input.id} className="tick">
        <input type="checkbox" checked={have.includes(input.id)} onChange={() => toggle(input.id)} />{" "}
        {name(input)} <span className="muted">({tag})</span>
      </label>
    );
  }

  return (
    <details
      className="method"
      onToggle={(e) => {
        if (e.currentTarget.open && combo === null) loadCombination(have);
      }}
    >
      <summary>{name(profile)}</summary>

      <div className="method-body">
        {SECTIONS.map(({ key, title }) => (
          <div key={key} className="row">
            <span className="muted">{title}: </span>
            {profile[key].length ? names(profile[key]) : <em>not recorded</em>}
          </div>
        ))}
        {combo && (
          <>
            <div className="row">
              <span className="muted">Role in a model: </span>
              {combo.roles.length ? names(combo.roles) : <em>not recorded</em>}
              {combo.complete_model && <span className="tag tag-soft"> complete model by itself</span>}
            </div>
            <div className="row">
              <span className="muted">Can run at: </span>
              {combo.supports_time_steps.length ? names(combo.supports_time_steps) : <em>not recorded</em>}
            </div>
          </>
        )}

        <h4 className="sub-title">1 · Add your data</h4>
        <strong>Which of these data do you already use?</strong>
        {profile.mandatory_inputs.length === 0 && profile.optional_inputs.length === 0 && (
          <div>
            <em>The ontology records no inputs for this method.</em>
          </div>
        )}
        {profile.mandatory_inputs.map((i) => tickBox(i, "required"))}
        {profile.optional_inputs.map((i) => tickBox(i, "optional"))}

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

        {combo === null && <p className="muted">Loading combinations…</p>}
        {combo && (
          <>
            <h4 className="sub-title">2 · Where the rest can come from</h4>
            {combo.inputs.length === 0 && <p className="muted">No input recorded.</p>}
            {combo.inputs.map((input) => (
              <Source key={`${input.kind}-${input.id}`} input={input} />
            ))}
            <div className={`verdict ${combo.alone.status === "runnable" ? "is-direct" : "is-complement"}`}>
              <strong>
                {combo.alone.status === "runnable"
                  ? "Can run on its own with your data and open data"
                  : "Needs another method before it"}
              </strong>
              {combo.alone.reasons.map((reason) => (
                <div key={reason}>{reason}</div>
              ))}
            </div>

            <h4 className="sub-title">3 · Combine it with other methods</h4>
            {software && (
              <p className="group-note">● = also available in the software you chose</p>
            )}
            <div className="row">
              <span className="muted">Methods that can feed it (upstream):</span>
              <Neighbours items={combo.fed_by} empty="None: it starts a chain." />
            </div>
            <div className="row">
              <span className="muted">Methods it can feed (downstream):</span>
              <Neighbours items={combo.feeds} empty="None: it ends a chain." />
            </div>
            <div className="row">
              <span className="muted">Methods doing the same job (alternatives):</span>
              <Neighbours items={combo.alternatives} empty="None recorded." />
            </div>

            <h4 className="sub-title">4 · Standard workflows that use it</h4>
            {combo.chains.length === 0 && (
              <p className="muted">No reference workflow uses this method yet.</p>
            )}
            {combo.chains.map((chain) => (
              <div key={chain.id} className="line">
                <strong>{name(chain)}</strong>
                {chain.same_software && <span className="tag tag-soft"> in your software</span>}
                <div className="muted">{chain.methods.map(name).join(" → ")}</div>
              </div>
            ))}
          </>
        )}
      </div>
    </details>
  );
}
