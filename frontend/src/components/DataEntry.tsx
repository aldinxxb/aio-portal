import { useEffect, useMemo, useRef, useState } from "react";
import type { Chain, Ref } from "../api";
import {
  assess,
  getDeclarable,
  getEntities,
  getLayer,
  getWatersheds,
  type Area,
  type AreaFeature,
  type AreaLayer,
  type Assessment,
  type DataItem,
  type DeclarableVariable,
  type Form,
  type LayerId,
  type Readiness,
  type Role,
  type WatershedLayer,
} from "../dataApi";
import ChainCard from "./ChainCard";
import { EntryHero, PageNav, PageSteps } from "./EntryFrame";
import FranceMap, { boundsOf, type Bounds } from "./FranceMap";
import { fullDataItems } from "../share";

// Entry "Start from data", the home screen of the portal. Four pages, one question each:
//   1 Study area     choose an area of France, then the watersheds (BD Topage) inside it
//   2 Your data      declare what you have · discover the open data of the area · role of each
//   3 Your goal      what your data enables · objective · expected output
//   4 Workflows      by readiness (with your data / with open data of the area / not ready),
//                    and the next dataset to add (adding one re-assesses everything)

const name = (item: Ref) => item.label ?? item.id;
const names = (items: Ref[]) => items.map(name).join(", ");

const LAYERS: { id: LayerId; title: string; one: string }[] = [
  { id: "basins", title: "River basins", one: "river basin" },
  { id: "subbasins", title: "Sub-basins", one: "sub-basin" },
  { id: "regions", title: "Regions", one: "region" },
  { id: "departments", title: "Departments", one: "department" },
];
const STEPS: Ref[] = [
  { id: "SubHourly", label: "sub-hourly" },
  { id: "Hourly", label: "hourly" },
  { id: "Daily", label: "daily" },
  { id: "MonthlyOrLonger", label: "monthly or longer" },
];
const FORMS: { id: Form; label: string; timed: boolean }[] = [
  { id: "series", label: "time series (stations)", timed: true },
  { id: "map", label: "map / grid", timed: true },
  { id: "points", label: "point measurements", timed: true },
  { id: "static", label: "static description", timed: false },
];
const STATIC_FORMS: { id: Form; label: string }[] = [
  { id: "map", label: "map / grid" },
  { id: "static", label: "table or value" },
];
const ROLES: { id: Role; title: string; help: string }[] = [
  { id: "forcing", title: "Forcing", help: "drives the model from outside (rain, temperature…)" },
  { id: "boundary", title: "Boundary condition", help: "a flow or level entering the model at its limits" },
  { id: "static", title: "Static description", help: "terrain, soil, land cover, parameters" },
  { id: "calibration", title: "Calibration", help: "observations to tune and check a model" },
  { id: "initial", title: "Initial state", help: "a starting condition" },
  { id: "unused", title: "Not used", help: "no method of the ontology uses it" },
];
const LEVELS: { id: Readiness; title: string; text: string; icon: string; css: string }[] = [
  { id: "hand", title: "Ready with your data", text: "every input is in your hands", icon: "✓", css: "lv-hand" },
  { id: "area", title: "Ready with open data of your area", text: "the rest is in open datasets covering your area", icon: "◎", css: "lv-area" },
  { id: "none", title: "Not ready here", text: "some input has no source in your area yet", icon: "⚠", css: "lv-none" },
];
const PAGES = [
  { title: "Study area", sub: "where you work" },
  { title: "Your data", sub: "and the open data of the area" },
  { title: "Your goal", sub: "challenge, objective, output" },
  { title: "Workflows", sub: "what you can run" },
];

const EMPTY_ITEM = { variable: "", step: "Daily", start: "", end: "", form: "series" as Form };

// The areas of the map as a list that can be filtered: a keyboard-friendly way to choose,
// and the place where a small area that is hard to click on the map is found by name.
function AreaList({ features, selected, onPick, placeholder }: {
  features: AreaFeature[]; selected: string[]; onPick: (f: AreaFeature) => void; placeholder: string;
}) {
  const [query, setQuery] = useState("");
  const words = query.trim().toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  const plain = (text: string) => text.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  const shown = words ? features.filter((f) => plain(f.properties.name).includes(words)) : features;
  return (
    <div className="area-list">
      <input className="area-find" type="search" placeholder={placeholder} value={query} onChange={(e) => setQuery(e.target.value)} />
      <div className="area-items" role="listbox" aria-label={placeholder}>
        {shown.length === 0 && <div className="muted area-none">No match</div>}
        {shown.slice(0, 300).map((f) => {
          const on = selected.includes(f.properties.id);
          return (
            <button key={f.properties.id} role="option" aria-selected={on} className={`area-item${on ? " on" : ""}`} onClick={() => onPick(f)}>
              <span className="area-tick">{on ? "✓" : ""}</span>{f.properties.name}
            </button>
          );
        })}
        {shown.length > 300 && <div className="muted area-none">{shown.length - 300} more: type to narrow</div>}
      </div>
    </div>
  );
}

// The variable to declare: type to search it by name (accents and case ignored), or open
// the list, grouped by the role the variable plays. Arrow keys and Enter work as in a list.
function VariablePicker({ variables, taken, value, onPick }: {
  variables: DeclarableVariable[]; taken: string[]; value: string; onPick: (id: string) => void;
}) {
  const plain = (text: string) => text.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  const chosen = variables.find((v) => v.id === value);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const words = plain(query).split(/\s+/).filter(Boolean);
  const free = variables.filter((v) => !taken.includes(v.id));
  const matches = words.length ? free.filter((v) => words.every((w) => plain(`${name(v)} ${v.id}`).includes(w))) : free;
  // grouped by role, in the order of ROLES; the flat order is the one the arrow keys follow
  const groups = ROLES.filter((r) => r.id !== "unused")
    .map((r) => ({ role: r, items: matches.filter((v) => v.role === r.id).sort((a, b) => name(a).localeCompare(name(b))) }))
    .filter((g) => g.items.length);
  const flat = groups.flatMap((g) => g.items);

  useEffect(() => {
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  useEffect(() => setActive(0), [query]);

  function pick(v: DeclarableVariable) {
    onPick(v.id);
    setQuery("");
    setOpen(false);
  }

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setActive((a) => Math.min(flat.length - 1, a + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
    else if (e.key === "Enter" && open && flat[active]) { e.preventDefault(); pick(flat[active]); }
    else if (e.key === "Escape") { setOpen(false); }
  }

  return (
    <div className="vpick" ref={box}>
      <input className="select wide vpick-input" type="text" role="combobox" aria-expanded={open} aria-autocomplete="list"
             placeholder={chosen ? name(chosen) : "search or choose a variable…"} value={open ? query : chosen ? name(chosen) : query}
             onFocus={() => { setOpen(true); setQuery(""); }} onChange={(e) => { setQuery(e.target.value); setOpen(true); }} onKeyDown={onKey} />
      <button type="button" className="vpick-toggle" tabIndex={-1} aria-label="Show the list" onMouseDown={(e) => { e.preventDefault(); setQuery(""); setOpen(!open); box.current?.querySelector("input")?.focus(); }}>▾</button>
      {open && (
        <div className="vpick-list" role="listbox">
          {flat.length === 0 && <div className="vpick-none">No variable matches “{query}”.</div>}
          {groups.map((g) => (
            <div key={g.role.id}>
              <div className="vpick-group">{g.role.title} <span className="muted">· {g.role.help}</span></div>
              {g.items.map((v) => {
                const index = flat.indexOf(v);
                return (
                  <button type="button" key={v.id} role="option" aria-selected={index === active}
                          className={`vpick-item${index === active ? " on" : ""}${v.id === value ? " chosen" : ""}`}
                          onMouseEnter={() => setActive(index)} onMouseDown={(e) => { e.preventDefault(); pick(v); }}>
                    <span>{name(v)}</span>
                    {v.datasets > 0 && <span className="vpick-meta">{v.datasets} open dataset{v.datasets > 1 ? "s" : ""}</span>}
                    {v.static && <span className="vpick-meta">static</span>}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// The study as kept in the address and in the draft: ids only, the rest is read again.
export type DataState = {
  page?: number; layer?: LayerId; area?: string; sheds?: string[]; entity?: string | null;
  data?: DataItem[]; challenge?: string | null; objective?: string | null; outputs?: string[]; level?: Readiness | null;
};

type Props = {
  // open a workflow's diagnosis, with the study described here
  onAdjust: (chain: Chain, study: { challenge: string; objective: string | null; outputs: string[]; data: DataItem[] }) => void;
  initial?: DataState | null;                                // a study from a link or a draft
  onState?: (state: DataState | null, summary: string) => void;   // every change, for the address (null: nothing chosen)
};

export default function DataEntry({ onAdjust, initial, onState }: Props) {
  const [page, setPage] = useState(initial?.page ?? 0);
  // the area of a link is found once its layer is loaded
  const pendingArea = useRef<string | null>(initial?.area ?? null);
  // ---- page 1: where ----
  const [layerId, setLayerId] = useState<LayerId>(initial?.layer ?? "basins");
  const [layer, setLayer] = useState<AreaLayer | null>(null);
  const [mapError, setMapError] = useState<string | null>(null);
  const [region, setRegion] = useState<{ layer: LayerId; feature: AreaFeature } | null>(null);
  const [sheds, setSheds] = useState<WatershedLayer | null>(null);
  const [shedError, setShedError] = useState<string | null>(null);
  const [picked, setPicked] = useState<string[]>(initial?.sheds ?? []);   // watersheds chosen inside the region
  const [entity, setEntity] = useState<string | null>(initial?.entity ?? null);
  const [entities, setEntities] = useState<Ref[]>([]);
  // ---- page 2: data ----
  const [variables, setVariables] = useState<DeclarableVariable[]>([]);
  const [data, setData] = useState<DataItem[]>(() => fullDataItems(initial?.data));
  const [item, setItem] = useState(EMPTY_ITEM);
  const [showAll, setShowAll] = useState(false);
  // ---- page 3: goal ----
  const [challenge, setChallenge] = useState<string | null>(initial?.challenge ?? null);
  const [objective, setObjective] = useState<string | null>(initial?.objective ?? null);
  const [outputs, setOutputs] = useState<string[]>(initial?.outputs ?? []);
  // ---- page 4: workflows ----
  const [level, setLevel] = useState<Readiness | null>(initial?.level ?? null);
  const [result, setResult] = useState<Assessment | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);

  useEffect(() => {
    getDeclarable().then(setVariables).catch(() => setVariables([]));
    getEntities().then(setEntities).catch(() => setEntities([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLayer(null);
    setMapError(null);
    getLayer(layerId)
      .then((found) => {
        if (cancelled) return;
        setLayer(found);
        // the area named by a link or a draft
        const wanted = pendingArea.current;
        if (wanted) {
          pendingArea.current = null;
          const feature = found.features.find((f) => f.properties.id === wanted);
          if (feature) setRegion({ layer: layerId, feature });
          else setPage(0);
        }
      })
      .catch((e) => { if (!cancelled) { pendingArea.current = null; setPage(0); setMapError(String(e)); } });
    return () => { cancelled = true; };
  }, [layerId]);

  // the watersheds of the chosen area, for the second map
  useEffect(() => {
    if (!region) return;
    let cancelled = false;
    setSheds(null);
    setShedError(null);
    getWatersheds(region.layer, region.feature.properties.id)
      .then((found) => { if (!cancelled) setSheds(found); })
      .catch((e) => { if (!cancelled) setShedError(String(e)); });
    return () => { cancelled = true; };
  }, [region]);

  // the study area sent to the assessment: the chosen watersheds, else the whole area
  const area: Area | null = useMemo(() => {
    if (!region) return null;
    const chosen = (sheds?.features ?? []).filter((f) => picked.includes(f.properties.id));
    if (chosen.length === 0) {
      const p = region.feature.properties;
      return { layer: region.layer, id: p.id, name: p.name, bbox: p.bbox };
    }
    const box = boundsOf(chosen.map((f) => f.properties.bbox), 0);
    return {
      layer: "watersheds", id: chosen.map((f) => f.properties.id).join("+"),
      name: chosen.length === 1 ? chosen[0].properties.name : `${chosen.length} watersheds of ${region.feature.properties.name}`,
      bbox: box,
    };
  }, [region, sheds, picked]);

  // everything is re-assessed whenever an answer changes (a little after, to group changes)
  const bodyKey = JSON.stringify({ area, entity, data, challenge, objective, outputs });
  useEffect(() => {
    if (!area) return;
    const mine = ++latest.current;
    const timer = setTimeout(() => {
      setBusy(true);
      assess({ area, entity, data, challenge, objective, outputs })
        .then((found) => { if (mine === latest.current) { setResult(found); setError(null); } })
        .catch((e) => { if (mine === latest.current) setError(String(e)); })
        .finally(() => { if (mine === latest.current) setBusy(false); });
    }, 200);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bodyKey]);

  const stateKey = JSON.stringify([page, region?.layer, region?.feature.properties.id, picked, entity, data, challenge, objective, outputs, level]);
  useEffect(() => {
    if (!onState || pendingArea.current) return;
    const state: DataState = {
      page, layer: region?.layer ?? layerId, area: region?.feature.properties.id, sheds: picked, entity,
      data, challenge, objective, outputs, level,
    };
    const summary = region
      ? `${area?.name ?? region.feature.properties.name} · ${data.length} data${challenge ? " · goal chosen" : ""}`
      : "";
    // nothing chosen yet: a plain address
    onState(region || data.length ? state : null, summary);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stateKey, area?.name]);

  const label = useMemo(() => new Map(variables.map((v) => [v.id, name(v)])), [variables]);
  const chosenVariable = variables.find((v) => v.id === item.variable);
  // a static variable (terrain, soil, land cover, parameters) has no time step and no period
  const isStatic = !!chosenVariable?.static || item.form === "static";

  function go(next: number) {
    setPage(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function pickRegion(feature: AreaFeature) {
    if (region?.feature.properties.id === feature.properties.id && region.layer === layerId) return;
    setRegion({ layer: layerId, feature });
    setPicked([]);
  }

  function toggleShed(feature: AreaFeature) {
    const id = feature.properties.id;
    setPicked(picked.includes(id) ? picked.filter((x) => x !== id) : [...picked, id]);
  }

  function pickVariable(id: string) {
    const v = variables.find((x) => x.id === id);
    setItem({ ...item, variable: id, form: v?.static ? (item.form === "static" ? "static" : "map") : item.form === "static" ? "series" : item.form });
  }

  function addItem() {
    if (!item.variable || data.some((d) => d.variable === item.variable)) return;
    setData([...data, {
      variable: item.variable, source: "own", dataset: null,
      step: isStatic ? null : item.step, form: item.form,
      start: !isStatic && item.start ? Number(item.start) : null, end: !isStatic && item.end ? Number(item.end) : null,
    }]);
    setItem({ ...EMPTY_ITEM, step: item.step, start: item.start, end: item.end });
  }

  function addDataset(dataset: Ref, provided: Ref[], step: string | null) {
    const known = new Set(data.map((d) => d.variable));
    const added = provided.filter((v) => !known.has(v.id)).map((v) => ({
      variable: v.id, source: "dataset" as const, dataset: dataset.id, step, start: null, end: null, form: null,
    }));
    // a finer forcing replaces the coarser one you had
    const replaced = data.map((d) => provided.some((v) => v.id === d.variable) && step
      ? { ...d, source: "dataset" as const, dataset: dataset.id, step } : d);
    setData([...replaced, ...added]);
    setLevel(null);
  }

  function pickChallenge(id: string) {
    if (id === challenge) return;
    setChallenge(id);
    setObjective(null);
    setOutputs([]);
  }

  const reachable = (i: number) =>
    i === 0 || (!!area && (i < 3 || (!!challenge && !!objective && outputs.length > 0)));

  const discovered = result?.discovered ?? [];
  const shownDatasets = showAll ? discovered : discovered.slice(0, 8);
  const flow = result?.workflows?.chains ?? [];
  const counts = Object.fromEntries(LEVELS.map((l) => [l.id, flow.filter((c) => c.readiness === l.id).length])) as Record<Readiness, number>;
  const openLevel = level ?? LEVELS.find((l) => counts[l.id] > 0)?.id ?? "hand";
  const regionLayer = LAYERS.find((l) => l.id === region?.layer);
  const shedBounds: Bounds | undefined = region ? boundsOf([region.feature.properties.bbox]) : undefined;
  const challengeName = challenge ? name(result?.enables.find((e) => e.id === challenge) ?? { id: challenge, label: null }) : null;

  return (
    <div className="dentry">
      <EntryHero
        kicker="I have data"
        title="What can you do with your data, here?"
        lead="Choose where you work and tell what data you have: the portal finds the open data covering your area, the role of each dataset, what it makes possible and what to add next."
        aside={area ? <span className="ehero-chip">📍 {area.name}</span> : undefined}
      />
      <PageSteps steps={PAGES} current={page} reachable={reachable} onGo={go} />

      {/* ================= 1. study area ================= */}
      {page === 0 && (
        <section className="dpage">
          <div className="dpage-head dpage-head-row">
            <div>
              <h3>{region ? "Refine with the watersheds of your area" : "Choose your study area"}</h3>
              <p className="muted">
                {region
                  ? "Topographic watersheds (bassins versants, BD Topage) inside your area. Click one or several to study them only, or keep the whole area."
                  : "Pick the kind of area, then click it on the map or in the list."}
              </p>
            </div>
            {!region && (
              <div className="seg" role="tablist">
                {LAYERS.map((l) => (
                  <button key={l.id} role="tab" aria-selected={layerId === l.id}
                          className={`seg-btn${layerId === l.id ? " on" : ""}`} onClick={() => setLayerId(l.id)}>
                    {l.title}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="map-grid">
            <div className="map-main">
              {!region && (
                <>
                  <FranceMap features={layer?.features ?? null} selected={[]} onSelect={pickRegion}
                             label="Map of metropolitan France" hint={`click to choose this ${LAYERS.find((l) => l.id === layerId)?.one}`} />
                  {mapError && <p className="error">The map could not be loaded ({mapError}). Try another layer.</p>}
                  {layer && <p className="fmap-note">{layer.note} · simplified boundaries</p>}
                </>
              )}
              {region && (
                <>
                  <FranceMap features={sheds?.features ?? null} selected={picked} onSelect={toggleShed}
                             bounds={shedBounds} outline={sheds?.area ?? region.feature} fine zoomable
                             label={`Watersheds of ${region.feature.properties.name}`} hint="click to add this watershed" />
                  {shedError && <p className="error">The watersheds could not be loaded ({shedError}). You can keep the whole area.</p>}
                  {sheds && (
                    <p className="fmap-note">
                      {sheds.features.length} watersheds · {sheds.note} ·{" "}
                      <a href={sheds.source} target="_blank" rel="noreferrer">metadata ↗</a>
                    </p>
                  )}
                </>
              )}
            </div>

            <aside className="map-side">
              {region && (
                <div className="mini-map">
                  <FranceMap features={layer?.features ?? null} selected={[region.feature.properties.id]}
                             onSelect={(f) => { setLayerId(region.layer); pickRegion(f); }} label="Your area in France" hint="click to change the area" />
                </div>
              )}
              <div className="area-card">
                <span className="area-kicker">Your study area</span>
                {!region && <span className="muted">Nothing chosen yet: click an area on the map.</span>}
                {region && area && (
                  <>
                    <strong className="area-name">{area.name}</strong>
                    <span className="muted">
                      {picked.length ? `inside the ${regionLayer?.one} ${region.feature.properties.name}` : `whole ${regionLayer?.one}`}
                      {" · "}{area.bbox[1].toFixed(2)}–{area.bbox[3].toFixed(2)}°N, {area.bbox[0].toFixed(2)}–{area.bbox[2].toFixed(2)}°E
                    </span>
                    {picked.length > 0 && (
                      <div className="held">
                        {(sheds?.features ?? []).filter((f) => picked.includes(f.properties.id)).map((f) => (
                          <span key={f.properties.id} className="held-chip">
                            {f.properties.name}
                            <button className="chip-x" title="Remove" onClick={() => toggleShed(f)}>×</button>
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="area-actions">
                      {picked.length > 0 && <button className="link-btn" onClick={() => setPicked([])}>Keep the whole {regionLayer?.one}</button>}
                      <button className="link-btn" onClick={() => { setRegion(null); setPicked([]); setSheds(null); }}>Choose another area</button>
                    </div>
                  </>
                )}
              </div>
              {!region && layer && (
                <AreaList features={layer.features} selected={[]} onPick={pickRegion}
                          placeholder={`Find a ${LAYERS.find((l) => l.id === layerId)?.one}…`} />
              )}
              {region && sheds && (
                <AreaList features={sheds.features} selected={picked} onPick={toggleShed} placeholder="Find a watershed…" />
              )}
              <label className="field">
                <span>Water entity <span className="muted">(optional)</span></span>
                <select className="select" value={entity ?? ""} onChange={(e) => setEntity(e.target.value || null)}>
                  <option value="">any</option>
                  {entities.map((e) => <option key={e.id} value={e.id}>{name(e)}</option>)}
                </select>
              </label>
              <button className="btn btn-primary" disabled={!area} onClick={() => go(1)}>Next: your data</button>
            </aside>
          </div>
        </section>
      )}

      {/* ================= 2. your data | open data | roles ================= */}
      {page === 1 && area && (
        <section className="dpage">
          <div className="dpage-head">
            <h3>Your data and the open data of {area.name}</h3>
            <p className="muted">Declare what you have; the portal lists the open datasets covering your area and the role each piece of data plays.</p>
          </div>
          <div className="data-grid">
            <div className="data-col">
              <div className="dcard">
                <div className="dcard-head"><span className="who who-you">You</span><h4>Declare your data in hand</h4></div>
                <div className={`declare${isStatic ? " is-static" : ""}`}>
                  <div className="dfield dfield-var"><span>Variable</span>
                  <VariablePicker variables={variables} taken={data.map((d) => d.variable)} value={item.variable} onPick={pickVariable} /></div>
                  <label className="dfield"><span>Form</span>
                  <select className="select" value={item.form} onChange={(e) => setItem({ ...item, form: e.target.value as Form })}>
                    {(chosenVariable?.static ? STATIC_FORMS : FORMS).map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
                  </select></label>
                  {!isStatic && (
                    <>
                      <label className="dfield"><span>Time step</span>
                      <select className="select" value={item.step} onChange={(e) => setItem({ ...item, step: e.target.value })}>
                        {STEPS.map((s) => <option key={s.id} value={s.id}>{name(s)}</option>)}
                      </select></label>
                      <div className="dfield"><span>Period</span>
                      <span className="years" title="period covered">
                        <input className="input" inputMode="numeric" placeholder="from" value={item.start}
                               onChange={(e) => setItem({ ...item, start: e.target.value.replace(/\D/g, "").slice(0, 4) })} />
                        <span className="muted">–</span>
                        <input className="input" inputMode="numeric" placeholder="to" value={item.end}
                               onChange={(e) => setItem({ ...item, end: e.target.value.replace(/\D/g, "").slice(0, 4) })} />
                      </span></div>
                    </>
                  )}
                  <button className="btn btn-primary dadd" disabled={!item.variable} onClick={addItem}>Add</button>
                </div>
                {item.variable && isStatic && (
                  <p className="muted small">A static description (terrain, soil, land cover, parameter) has no time step or period.</p>
                )}
                {data.length === 0 && <p className="muted small">Nothing declared yet: you can also continue with open data only.</p>}
                <div className="held">
                  {data.map((d) => (
                    <span key={d.variable} className={`held-chip${d.source === "dataset" ? " from-dataset" : ""}`}>
                      <strong>{label.get(d.variable) ?? d.variable}</strong>
                      <span className="muted">
                        {d.source === "dataset" ? `from ${d.dataset}` : FORMS.find((f) => f.id === d.form)?.label}
                        {d.step ? ` · ${STEPS.find((s) => s.id === d.step)?.label}` : ""}
                        {d.start || d.end ? ` · ${d.start ?? "…"}–${d.end ?? "…"}` : ""}
                      </span>
                      <button className="chip-x" title="Remove" onClick={() => setData(data.filter((x) => x.variable !== d.variable))}>×</button>
                    </span>
                  ))}
                </div>
              </div>

              <div className="dcard">
                <div className="dcard-head"><span className="who who-sys">System</span><h4>Role of your data</h4></div>
                {data.length === 0 ? (
                  <p className="muted small">Declare data to see the role each one plays in a model: forcing, boundary condition, static description, calibration or initial state.</p>
                ) : (
                  <div className="roles">
                    {ROLES.map((r) => {
                      const items = (result?.roles ?? []).filter((x) => x.roles.includes(r.id));
                      if (!items.length) return null;
                      return (
                        <div key={r.id} className={`role-col rc-${r.id}`}>
                          <div className="role-col-head"><strong>{r.title}</strong><span className="muted">{r.help}</span></div>
                          {items.map((x) => (
                            <div key={x.id} className={`role-item${x.source === "dataset" ? " from-dataset" : ""}`}>
                              <strong>{name(x)}</strong>
                              <span className="muted">used by {x.methods} method(s) · {x.workflows} workflow(s)</span>
                            </div>
                          ))}
                        </div>
                      );
                    })}
                  </div>
                )}
                {result?.data_step && (
                  <p className="group-note">Your forcing data is {name(result.data_step)}: workflows needing finer data are flagged.</p>
                )}
              </div>
            </div>

            <div className="dcard">
              <div className="dcard-head"><span className="who who-sys">System</span><h4>Open data covering your area</h4></div>
              {!result && <p className="muted">Looking in the catalogue…</p>}
              {result && (
                <>
                  <div className="supply">
                    <span className="supply-n">{result.supply.datasets}</span>
                    <span>datasets cover your area <span className="muted">({result.supply.full} fully)</span>,
                      giving <strong>{result.supply.variables}</strong> variables</span>
                  </div>
                  <div className="disc-list">
                    {shownDatasets.map((d) => (
                      <div key={d.id} className="disc">
                        <div className="disc-head">
                          <strong>{name(d)}</strong>
                          {d.url && /^https?:/.test(d.url) && <a className="data-link" href={d.url} target="_blank" rel="noreferrer">↗</a>}
                          <span className={`cov cov-${d.coverage}`}>{d.coverage === "full" ? "covers the area" : "covers part of it"}</span>
                          {d.measured && <span className="cov cov-meas">measured</span>}
                          {d.period && d.period !== "full" && <span className="cov cov-partial">{d.period === "none" ? "outside your period" : "part of your period"}</span>}
                        </div>
                        <div className="muted disc-meta">
                          {names(d.publishers)} · {d.start ? d.start.slice(0, 4) : "?"}–{d.ongoing ? "today" : d.end ? d.end.slice(0, 4) : "?"}
                          {d.temporal_nature ? ` · ${d.temporal_nature}` : ""}
                        </div>
                        <div className="disc-vars">{d.variables.slice(0, 6).map((v) => <span key={v.id} className="pill">{name(v)}</span>)}
                          {d.variables.length > 6 && <span className="muted">+{d.variables.length - 6}</span>}</div>
                      </div>
                    ))}
                  </div>
                  {discovered.length > 8 && (
                    <button className="link-btn" onClick={() => setShowAll(!showAll)}>
                      {showAll ? "Show fewer" : `Show the ${discovered.length - 8} others`}
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
          <PageNav onBack={() => go(0)} onNext={() => go(2)} nextLabel="Next: your goal"
                   note={data.length ? `${data.length} variable(s) declared` : "no data declared: open data only"} />
        </section>
      )}

      {/* ================= 3. what it enables · objective · output ================= */}
      {page === 2 && area && (
        <section className="dpage">
          <div className="dpage-head">
            <h3>What your data enables, and what you want from it</h3>
            <p className="muted">Each challenge shows how many workflows can run with your data and the open data of {area.name}. Pick one, then the objective and the expected output.</p>
          </div>

          <div className="goal-step">
            <div className="goal-n">1</div>
            <div className="goal-body">
              <h4>Water challenge</h4>
              {!result && <p className="muted">Assessing…</p>}
              <div className="enable-grid">
                {(result?.enables ?? []).map((e) => {
                  const total = e.workflows || 1;
                  return (
                    <button key={e.id} className={`enable${challenge === e.id ? " on" : ""}`} onClick={() => pickChallenge(e.id)}>
                      <span className="enable-name">{name(e)}</span>
                      <span className="enable-bar">
                        <i className="lv-hand" style={{ width: `${(e.hand / total) * 100}%` }} />
                        <i className="lv-area" style={{ width: `${(e.area / total) * 100}%` }} />
                      </span>
                      <span className="enable-n">
                        <strong>{e.hand + e.area}</strong> of {e.workflows} workflows runnable
                        {e.hand > 0 && <> · {e.hand} with your data alone</>}
                      </span>
                      {e.outputs.length > 0 && (
                        <span className="enable-outs">{e.outputs.slice(0, 4).map((o) => (
                          <span key={o.id} className={`pill ${o.level === "hand" ? "pill-hit" : "pill-open"}`}>{name(o)}</span>
                        ))}</span>
                      )}
                      <span className="enable-go">{challenge === e.id ? "✓ chosen" : "choose"}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {challenge && (
            <div className="goal-step">
              <div className="goal-n">2</div>
              <div className="goal-body">
                <h4>Study objective <span className="muted">· for {challengeName}</span></h4>
                {!result?.objectives && <p className="muted">Assessing…</p>}
                <div className="options">
                  {(result?.objectives ?? []).map((o) => (
                    <button key={o.id} className={`opt${objective === o.id ? " selected" : ""}${o.hand + o.area > 0 ? " opt-direct" : ""}`}
                            disabled={o.hand + o.area === 0 && o.workflows === 0}
                            onClick={() => { setObjective(o.id); setOutputs([]); }}>
                      <span>{name(o)}</span>
                      <span className="count" title="workflows runnable for this objective">{o.hand + o.area}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {challenge && objective && (
            <div className="goal-step">
              <div className="goal-n">3</div>
              <div className="goal-body">
                <h4>Expected output <span className="muted">· pick one or several</span></h4>
                {!result?.outputs && <p className="muted">Assessing…</p>}
                <div className="out-grid">
                  {(result?.outputs ?? []).map((o) => {
                    const on = outputs.includes(o.id);
                    const reach = o.hand + o.area;
                    return (
                      <button key={o.id} className={`out${on ? " on" : ""}${reach ? "" : " off"}`}
                              onClick={() => setOutputs(on ? outputs.filter((x) => x !== o.id) : [...outputs, o.id])}>
                        <span className="out-head">
                          <strong>{name(o)}</strong>
                          {o.suggested && <span className="out-star">★ suggested</span>}
                          {o.entity_match && <span className="pill">your water entity</span>}
                        </span>
                        {o.question && <span className="out-q">“{o.question}”</span>}
                        <span className="muted">{reach ? `${reach} runnable workflow(s)` : "no runnable workflow here yet"} · from {names(o.variables)}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
          <PageNav onBack={() => go(1)} onNext={() => { setLevel(null); go(3); }} nextLabel="See the workflows"
                   nextDisabled={!challenge || !objective || outputs.length === 0}
                   note={!challenge ? "choose a challenge" : !objective ? "choose an objective" : outputs.length === 0 ? "choose an expected output" : undefined} />
        </section>
      )}

      {/* ================= 4. workflows by readiness, next dataset ================= */}
      {page === 3 && area && challenge && (
        <section className="dpage">
          <div className="study-line">
            <span>📍 <strong>{area.name}</strong></span>
            <span><strong>{challengeName}</strong> · {name(result?.objectives?.find((o) => o.id === objective) ?? { id: objective ?? "", label: null })}</span>
            <span>{names((result?.outputs ?? []).filter((o) => outputs.includes(o.id)))}</span>
            <span className="muted">{data.length} variable(s) in hand</span>
            <button className="link-btn" onClick={() => go(2)}>change</button>
          </div>

          {!result?.workflows && <p className="muted">Looking for workflows…</p>}
          {result?.workflows && (
            <>
              <div className="level-tiles" role="tablist">
                {LEVELS.map((l) => (
                  <button key={l.id} role="tab" aria-selected={openLevel === l.id}
                          className={`level-tile ${l.css}${openLevel === l.id ? " on" : ""}`} onClick={() => setLevel(l.id)}>
                    <span className="level-icon">{l.icon}</span>
                    <span className="level-n">{counts[l.id]}</span>
                    <span className="level-title">{l.title}</span>
                    <span className="level-text">{l.text}</span>
                  </button>
                ))}
              </div>

              {openLevel !== "hand" && (result.next_datasets ?? []).length > 0 && (
                <div className="next">
                  <div className="next-title">Next dataset to add <span className="muted">· covering {area.name}, to move workflows up</span></div>
                  <div className="next-grid">
                    {(result.next_datasets ?? []).map((n) => (
                      <div key={n.dataset.id} className="next-card">
                        <div className="next-head">
                          <strong>{name(n.dataset)}</strong>
                          {n.dataset.url && /^https?:/.test(n.dataset.url) && <a className="data-link" href={n.dataset.url} target="_blank" rel="noreferrer">↗</a>}
                        </div>
                        <div className="muted">{names(n.dataset.publishers)}</div>
                        {n.provides.length > 0 && <div>Brings <strong>{names(n.provides)}</strong></div>}
                        {n.finer.length > 0 && <div>Finer <strong>{names(n.finer)}</strong> ({n.finer[0].time_steps.join(" / ")})</div>}
                        <div className="muted">
                          {n.completes.length > 0 ? `Completes ${n.completes.length} workflow(s)` : ""}
                          {n.completes.length > 0 && n.helps.length > 0 ? " · " : ""}
                          {n.helps.length > 0 ? `helps ${n.helps.length}` : ""}
                        </div>
                        <button className="btn btn-primary"
                                onClick={() => addDataset(n.dataset, [...n.provides, ...n.finer],
                                  n.finer.length ? (n.finer[0].time_steps[0]?.includes("hour") ? "Hourly" : n.finer[0].time_steps[0]?.includes("min") ? "SubHourly" : null) : null)}>
                          Add to my data
                        </button>
                      </div>
                    ))}
                  </div>
                  <p className="loop-note">↻ Adding a dataset re-assesses every workflow.</p>
                </div>
              )}

              {LEVELS.filter((l) => l.id === openLevel).map((l) => {
                const items = flow.filter((c) => c.readiness === l.id);
                return (
                  <div key={l.id} className="level-page">
                    <h4 className="level-page-title"><span className={`level-dot ${l.css}`}>{l.icon}</span> {l.title}</h4>
                    {items.length === 0 && (
                      <p className="muted empty-note">
                        {l.id === "hand" ? "No workflow runs with your data alone yet: see the ones ready with open data, or add data."
                          : l.id === "area" ? "No workflow becomes ready with the open data of your area."
                          : "Every workflow can run here."}
                      </p>
                    )}
                    {items.map((c, i) => (
                      <ChainCard key={c.id} chain={c} open={i === 0}
                                 onAdjust={(chain) => onAdjust(chain, { challenge: challenge!, objective, outputs, data })} />
                    ))}
                  </div>
                );
              })}
            </>
          )}
          <PageNav onBack={() => go(2)} />
        </section>
      )}

      {busy && <div className="busy">Updating…</div>}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
