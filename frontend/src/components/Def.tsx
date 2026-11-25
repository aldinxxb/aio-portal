import { useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { getTerm } from "../ontologyApi";
import { GLOSSARY, type GlossaryKey } from "../glossary";

// A technical word with its explanation: dotted underline, explanation on hover or focus (and on
// a tap on phones), with a link to the term in the AIO ontology. See glossary.ts.

const quoted = new Map<string, Promise<string | null>>();   // ontology definitions, fetched once
function ontologyDefinition(id: string): Promise<string | null> {
  if (!quoted.has(id)) quoted.set(id, getTerm(id).then((t) => t.definition ?? null).catch(() => null));
  return quoted.get(id)!;
}

export default function Def({ k, children }: { k: GlossaryKey; children?: ReactNode }) {
  const entry = GLOSSARY[k] as (typeof GLOSSARY)[GlossaryKey] & { fromOntology?: boolean };
  const [open, setOpen] = useState(false);
  const [quote, setQuote] = useState<string | null>(null);
  const id = useId();
  const closing = useRef<number | null>(null);
  const pop = useRef<HTMLSpanElement>(null);
  // keep the explanation on screen: shifted left near the right edge, never past the left one
  useLayoutEffect(() => {
    const el = pop.current;
    if (!open || !el) return;
    el.style.transform = "";
    const r = el.getBoundingClientRect();
    const zoom = r.width / (el.offsetWidth || r.width) || 1;      // the page may be scaled (big screens)
    const room = document.documentElement.clientWidth - 8;
    let dx = 0;
    if (r.right > room) dx = room - r.right;
    if (r.left + dx < 8) dx = 8 - r.left;
    if (dx) el.style.transform = `translateX(${dx / zoom}px)`;
  }, [open]);

  function show() {
    if (closing.current) { window.clearTimeout(closing.current); closing.current = null; }
    setOpen(true);
    if (entry.fromOntology && entry.term && quote === null) ontologyDefinition(entry.term).then((d) => setQuote(d ?? ""));
  }
  // a short delay, so the pointer can move into the explanation to follow its link
  const hide = () => { closing.current = window.setTimeout(() => setOpen(false), 150); };

  return (
    <span className="def" onMouseEnter={show} onMouseLeave={hide}>
      <span className="def-word" tabIndex={0} role="button" aria-describedby={open ? id : undefined} aria-expanded={open}
            onFocus={(e) => { if (e.currentTarget.matches(":focus-visible")) show(); }} onBlur={hide} onClick={(e) => { e.preventDefault(); e.stopPropagation(); if (open) setOpen(false); else show(); }}
            onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}>
        {children ?? entry.label}
      </span>
      {open && (
        <span className="def-pop" role="tooltip" id={id} ref={pop} onMouseEnter={show} onMouseLeave={hide}>
          <strong className="def-title">{entry.label}</strong>
          <span className="def-text">{entry.text}</span>
          {quote && <span className="def-quote">AIO ontology: “{quote}”</span>}
          {entry.term && (
            <a className="def-link" href={`#/ontology/${encodeURIComponent(entry.term)}`} target="_blank" rel="noreferrer"
               onClick={(e) => e.stopPropagation()} title="Opens in a new tab: your page stays as it is">
              See it in the AIO ontology ↗
            </a>
          )}
        </span>
      )}
    </span>
  );
}
