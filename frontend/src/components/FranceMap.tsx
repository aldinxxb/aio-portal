import { useEffect, useMemo, useRef, useState } from "react";
import type { AreaFeature } from "../dataApi";

// A map drawn in SVG from simplified boundaries served by the backend. Without `bounds` it
// shows metropolitan France; with `bounds` it zooms on a study area (its watersheds).
// Equirectangular projection, x scaled by cos(latitude) so shapes keep their proportions.
// With `zoomable`: mouse wheel or +/− to zoom (around the cursor), drag to move.
export type Bounds = [number, number, number, number];   // lon0, lat0, lon1, lat1
const FRANCE: Bounds = [-5.3, 41.25, 9.7, 51.2];
const MAX_ZOOM = 16;

// soft tints of the AIO logo colours (blue, sand, green), so neighbours are told apart
const PALETTE = ["#dbe8f6", "#f8e7c9", "#dcefd8", "#c9dcf0", "#f3dcb4", "#cbe5c6", "#e8f1fa", "#fbf0dc", "#e6f3e3", "#d4e3f3"];

function projection(bounds: Bounds, width: number) {
  const [lon0, lat0, lon1, lat1] = bounds;
  const scaleX = Math.cos((((lat0 + lat1) / 2) * Math.PI) / 180);
  const k = width / ((lon1 - lon0) * scaleX);
  const height = Math.round((lat1 - lat0) * k);
  const x = (lon: number) => (lon - lon0) * scaleX * k;
  const y = (lat: number) => (lat1 - lat) * k;
  const path = (feature: AreaFeature) =>
    feature.geometry.coordinates
      .map((polygon) => polygon.map((ring) => "M" + ring.map(([lon, lat]) => `${x(lon).toFixed(1)},${y(lat).toFixed(1)}`).join("L") + "Z").join(""))
      .join("");
  return { height, path };
}

// a box around some features, a little wider so they do not touch the edge
export function boundsOf(boxes: Bounds[], margin = 0.06): Bounds {
  const lon0 = Math.min(...boxes.map((b) => b[0]));
  const lat0 = Math.min(...boxes.map((b) => b[1]));
  const lon1 = Math.max(...boxes.map((b) => b[2]));
  const lat1 = Math.max(...boxes.map((b) => b[3]));
  const dx = (lon1 - lon0) * margin || 0.05;
  const dy = (lat1 - lat0) * margin || 0.05;
  return [lon0 - dx, lat0 - dy, lon1 + dx, lat1 + dy];
}

type View = { x: number; y: number; w: number; h: number };

type Props = {
  features: AreaFeature[] | null;   // null while loading
  selected: string[];               // ids of the chosen features
  onSelect: (feature: AreaFeature) => void;
  bounds?: Bounds;                  // zoom; France when absent
  outline?: AreaFeature | null;     // drawn on top, not clickable (the study area around its watersheds)
  hint?: string;                    // what a click does
  fine?: boolean;                   // many small features: thinner lines
  zoomable?: boolean;               // wheel / buttons to zoom, drag to move
  label?: string;                   // aria label
};

export default function FranceMap({ features, selected, onSelect, bounds = FRANCE, outline, hint = "click to choose", fine, zoomable, label }: Props) {
  const [hover, setHover] = useState<AreaFeature | null>(null);
  const width = 1000;
  const { height, path } = useMemo(() => projection(bounds, width), [bounds]);
  const full: View = useMemo(() => ({ x: 0, y: 0, w: width, h: height }), [height]);
  const [view, setView] = useState<View>(full);
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<{ x: number; y: number; view: View; moved: boolean } | null>(null);
  const moved = useRef(false);          // the last press was a drag: do not treat it as a click

  useEffect(() => setView(full), [full]);

  const paths = useMemo(
    () => (features ?? []).map((f) => ({ feature: f, d: path(f) })),
    [features, path],
  );
  const chosen = paths.filter((p) => selected.includes(p.feature.properties.id));
  const outlinePath = useMemo(() => (outline ? path(outline) : null), [outline, path]);
  const shown = hover ?? (chosen.length === 1 ? chosen[0].feature : null);
  const zoom = width / view.w;

  // keep the view inside the map, and between 1x and MAX_ZOOM
  function clamp(next: View): View {
    const w = Math.min(full.w, Math.max(full.w / MAX_ZOOM, next.w));
    const h = (w / full.w) * full.h;
    const x = Math.min(full.w - w, Math.max(0, next.x));
    const y = Math.min(full.h - h, Math.max(0, next.y));
    return { x, y, w, h };
  }

  // zoom by `factor` (>1 = in) around a point given in map coordinates
  function zoomAt(factor: number, cx = view.x + view.w / 2, cy = view.y + view.h / 2) {
    setView((v) => {
      const w = v.w / factor;
      const h = v.h / factor;
      return clamp({ x: cx - ((cx - v.x) * w) / v.w, y: cy - ((cy - v.y) * h) / v.h, w, h });
    });
  }

  function toMap(clientX: number, clientY: number) {
    const svg = svgRef.current;
    const matrix = svg?.getScreenCTM();
    if (!svg || !matrix) return { x: view.x + view.w / 2, y: view.y + view.h / 2 };
    const point = new DOMPoint(clientX, clientY).matrixTransform(matrix.inverse());
    return { x: point.x, y: point.y };
  }

  // the wheel must not scroll the page while the cursor is on the map
  useEffect(() => {
    const svg = svgRef.current;
    if (!zoomable || !svg) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const p = toMap(event.clientX, event.clientY);
      zoomAt(event.deltaY < 0 ? 1.25 : 1 / 1.25, p.x, p.y);
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  });

  function onPointerDown(event: React.PointerEvent) {
    if (!zoomable) return;
    drag.current = { x: event.clientX, y: event.clientY, view, moved: false };
    moved.current = false;
  }
  function onPointerMove(event: React.PointerEvent) {
    const d = drag.current;
    if (!d || !svgRef.current) return;
    const dx = event.clientX - d.x;
    const dy = event.clientY - d.y;
    if (!d.moved && Math.hypot(dx, dy) < 4) return;
    d.moved = true;
    moved.current = true;
    // screen pixels per map unit, as drawn (the map may be centred with margins when its height is capped)
    const m = svgRef.current.getScreenCTM();
    const scale = m && m.a ? 1 / m.a : d.view.w / svgRef.current.getBoundingClientRect().width;
    setView(clamp({ ...d.view, x: d.view.x - dx * scale, y: d.view.y - dy * scale }));
  }
  function onPointerUp() {
    drag.current = null;
  }

  function pick(feature: AreaFeature) {
    if (moved.current) return;          // the end of a drag, not a click
    onSelect(feature);
  }

  return (
    <div className={`fmap${fine ? " fmap-fine" : ""}${zoomable ? " fmap-zoomable" : ""}`}>
      <svg ref={svgRef} viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`} className="fmap-svg" role="img" aria-label={label ?? "Map"}
           onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerLeave={onPointerUp}
           style={{ aspectRatio: `${width} / ${height}` }}>
        <rect width={width} height={height} rx={14} className="fmap-sea" />
        {paths.map(({ feature, d }, index) => {
          const id = feature.properties.id;
          return (
            <path key={id} d={d} style={{ "--fill": PALETTE[index % PALETTE.length] } as React.CSSProperties}
                  vectorEffect="non-scaling-stroke"
                  className={`fmap-area${selected.includes(id) ? " on" : ""}${hover?.properties.id === id ? " hover" : ""}`}
                  onMouseEnter={() => setHover(feature)} onMouseLeave={() => setHover(null)}
                  onClick={() => pick(feature)}>
              <title>{feature.properties.name}</title>
            </path>
          );
        })}
        {outlinePath && <path d={outlinePath} className="fmap-outline" vectorEffect="non-scaling-stroke" pointerEvents="none" />}
        {/* the chosen areas drawn again on top, so their outline is never hidden */}
        {chosen.map(({ feature, d }) => (
          <path key={`c-${feature.properties.id}`} d={d} className="fmap-chosen" vectorEffect="non-scaling-stroke" pointerEvents="none" />
        ))}
      </svg>
      {zoomable && (
        <div className="fmap-zoom" role="group" aria-label="Zoom">
          <button title="Zoom in" onClick={() => zoomAt(1.6)} disabled={zoom >= MAX_ZOOM - 0.01}>+</button>
          <button title="Zoom out" onClick={() => zoomAt(1 / 1.6)} disabled={zoom <= 1.01}>−</button>
          <button title="Whole area" onClick={() => setView(full)} disabled={zoom <= 1.01}>⤢</button>
          {zoom > 1.01 && <span className="fmap-zoom-level">×{zoom.toFixed(1)}</span>}
        </div>
      )}
      {!features && <div className="fmap-wait">Loading the map…</div>}
      {shown && (
        <div className="fmap-label">
          <strong>{shown.properties.name}</strong>
          <span className="muted">
            {hover && !selected.includes(hover.properties.id) ? hint : selected.includes(shown.properties.id) ? "chosen · click to remove" : hint}
          </span>
        </div>
      )}
      {zoomable && <div className="fmap-help">Scroll to zoom · drag to move</div>}
    </div>
  );
}
