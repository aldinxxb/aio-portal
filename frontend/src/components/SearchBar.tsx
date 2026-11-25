import { useEffect, useMemo, useRef, useState } from "react";
import { loadIndex, suggest, type Go, type Index } from "../searchIndex";

// The header search: a question in plain words, answered by where to go. Each suggestion opens
// an entry already filled in (see searchIndex.ts). Arrow keys and Enter work as in a list.
export default function SearchBar({ onGo }: { onGo: (go: Go) => void }) {
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [index, setIndex] = useState<Index | null>(null);
  const [failed, setFailed] = useState(false);
  const [active, setActive] = useState(0);
  const box = useRef<HTMLFormElement>(null);

  // the vocabulary is loaded on the first use only
  function warm() {
    if (index || failed) return;
    loadIndex().then(setIndex).catch(() => setFailed(true));
  }

  const found = useMemo(() => (index && text.trim().length >= 2 ? suggest(index, text) : []), [index, text]);
  useEffect(() => {
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  function go(i: number) {
    const s = found[i];
    if (!s) return;
    onGo(s.go);
    setOpen(false);
    setText("");
    (document.activeElement as HTMLElement | null)?.blur();
  }

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setActive((a) => Math.min(found.length - 1, a + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
    else if (e.key === "Escape") { setOpen(false); }
  }

  const showList = open && text.trim().length >= 2;
  return (
    <form className="search" ref={box} role="search" onSubmit={(e) => { e.preventDefault(); go(active); }}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
        <circle cx="11" cy="11" r="7" />
        <path d="M20 20l-3.5-3.5" />
      </svg>
      <input type="search" value={text} role="combobox" aria-expanded={showList} aria-autocomplete="list" aria-controls="search-list"
             aria-label="Ask where to start: a water problem, an output, your data or a model"
             placeholder="e.g. flood hazard map with my rainfall data, or HEC-HMS"
             onFocus={() => { warm(); setOpen(true); }} onChange={(e) => { setText(e.target.value); setActive(0); setOpen(true); warm(); }} onKeyDown={onKey} />
      <button className="search-btn" type="submit" disabled={!found.length}>Search</button>
      {showList && (
        <div className="search-list" id="search-list" role="listbox">
          {!index && !failed && <div className="search-none">Reading the portal's vocabulary…</div>}
          {failed && <div className="search-none">The search could not reach the portal's service. Try again in a moment.</div>}
          {found.map((s, i) => {
            const head = i === 0 || found[i - 1].group !== s.group ? s.group : null;
            return (
              <div key={s.key}>
                {head && <div className="search-group">{head}</div>}
                <button type="button" role="option" aria-selected={i === active} className={`search-item${i === active ? " on" : ""}${s.group === "Best start" ? " best" : ""}`}
                        onMouseEnter={() => setActive(i)} onMouseDown={(e) => { e.preventDefault(); go(i); }}>
                  <span className="search-title">{s.title}</span>
                  {s.detail && <span className="search-detail">{s.detail}</span>}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </form>
  );
}
