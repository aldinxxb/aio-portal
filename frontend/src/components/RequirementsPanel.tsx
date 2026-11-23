import type { ExcludedMethod, Requirement } from "../api";

// What each kind of rule does today. Only method rules change the ranking.
function tagOf(requirement: Requirement): { text: string; className: string } {
  if (requirement.kind !== "method") {
    const what = requirement.kind === "data" ? "data rule" : "display rule";
    return { text: `${what} · for information`, className: "tag-info" };
  }
  return requirement.strength === "hard"
    ? { text: "required · removes methods", className: "tag-hard" }
    : { text: "preferred · changes the score", className: "tag-soft" };
}

type Props = {
  requirements: Requirement[];     // the rules implied by the user's choices
  excluded: ExcludedMethod[];      // the methods a required rule removed, with why
  text: (id: string) => string;    // id -> readable name
};

export default function RequirementsPanel({ requirements, excluded, text }: Props) {
  if (requirements.length === 0) return null;

  return (
    <>
      <details className="rules" open>
        <summary>What your choices require ({requirements.length})</summary>
        {requirements.map((requirement) => {
          const tag = tagOf(requirement);
          return (
            <div key={requirement.id} className="rule">
              <span className="rule-label">{requirement.label ?? requirement.id}</span>{" "}
              <span className={`tag ${tag.className}`}>{tag.text}</span>
              {requirement.rationale && <div>{requirement.rationale}</div>}
              <div className="rule-why">
                Because you chose: {requirement.because.map(text).join(", ")}
              </div>
            </div>
          );
        })}
      </details>

      {excluded.length > 0 && (
        <details className="rules">
          <summary>{excluded.length} method(s) removed by a required rule</summary>
          {excluded.map((method) => (
            <div key={method.id} className="rule">
              <span className="rule-label">{method.label ?? method.id}</span>
              <ul className="reasons">
                {method.reasons.map((reason) => (
                  <li key={reason.requirement} className="reason-fail">
                    ✗ {reason.label ?? reason.requirement}: {reason.detail}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </details>
      )}
    </>
  );
}
