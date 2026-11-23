import { useEffect, useState } from "react";
import type { Chain, ChainRecommendation, Licence } from "../api";
import { EMPTY_REQUEST, setupOptions, type SetupOption } from "../setupApi";
import ChainCard from "./ChainCard";

type Props = {
  chains: ChainRecommendation | null;   // null while loading
  licence: Licence;                     // the software licence filter
  onLicence: (licence: Licence) => void;
  software: string | null;              // the software the user works in (null = any)
  onSoftware: (software: string | null) => void;
  onAdjust: (chain: Chain) => void;     // open a workflow in the diagnosis
};

// A workflow is a CHAIN of methods (loss -> transform -> routing -> hydraulics ...),
// because one method rarely answers a question alone. Standard-practice chains come
// first; chains the portal builds from the ontology follow and are labelled as such.
export default function WorkflowSection({ chains, licence, onLicence, software, onSoftware, onAdjust }: Props) {
  const found = chains?.chains ?? [];
  const [softwares, setSoftwares] = useState<SetupOption[]>([]);
  useEffect(() => {
    setupOptions<{ options: SetupOption[] }>("software", EMPTY_REQUEST)
      .then((r) => setSoftwares(r.options))
      .catch(() => setSoftwares([]));
  }, []);
  const ready = found.filter((c) => c.status === "runnable").length;

  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2 className="panel-title">Recommended workflows</h2>
            <p className="panel-sub">
              Combinations of methods that answer your challenge together. Open one, then click a
              step to see its inputs, parameters and outputs.
            </p>
          </div>
          <label className="compare-mode">
            Your software
            <select className="select" value={software ?? ""} onChange={(e) => onSoftware(e.target.value || null)}>
              <option value="">any software</option>
              {softwares.map((s) => (
                <option key={s.id} value={s.id}>{s.label ?? s.id}</option>
              ))}
            </select>
          </label>
          <label className="compare-mode">
            Licence
            <select
              className="select"
              value={licence ?? ""}
              onChange={(e) => onLicence((e.target.value || null) as Licence)}
            >
              <option value="">any licence</option>
              <option value="free">free of charge only</option>
              <option value="open">open source only</option>
            </select>
          </label>
        </div>

        {chains === null && <p className="muted">Building workflows…</p>}
        {chains?.note && <p className="group-note">{chains.note}</p>}
        {chains !== null && found.length === 0 && (
          <p className="muted">
            No workflow fits these choices. Try another software or licence, or remove an expected output.
          </p>
        )}
        {found.length > 0 && (
          <p className="meta">
            {found.length} workflow(s) · {ready} ready to run with your data and open data
          </p>
        )}

        <div className="flow-groups">
          {found.map((chain, index) => (
            <ChainCard key={chain.id} chain={chain} open={index === 0} onAdjust={onAdjust} />
          ))}
        </div>
      </section>

    </>
  );
}
