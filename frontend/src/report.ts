// The report of a diagnosis: the study, the verdict, the workflow, its data and where each
// piece comes from, the checks, what was changed and what is left to do.
//
// One model, two renderings:
//   - a printable page (with the set-up diagram), opened in a new window: "Save as PDF"
//   - a Markdown file, for a project wiki, a repository or an e-mail
// Both carry the link that reopens the same study in the portal.

import type { Ref } from "./api";
import type { Action, DataRow, Diagnosis, Improvement } from "./setupApi";
import { KIND, NATURE, STATUS, derivationText, name, names, sourceOf } from "./setupLabels";

export type ReportContext = {
  accepted: string[];                 // changes accepted during the session, oldest first
  declined: string[];                 // ids of the suggestions declined
  link: string;                       // reopens this study in the portal
  diagram: string | null;             // the set-up diagram, as SVG markup (printable page only)
  styles: string;                     // the portal's styles, so the diagram looks the same
};

// ---- the model -------------------------------------------------------------------------

type Cell = string | { text: string; href?: string | null; tone?: "ok" | "open" | "warn" | "muted" };
type Block =
  | { kind: "facts"; rows: [string, Cell][] }
  | { kind: "table"; head: string[]; rows: Cell[][] }
  | { kind: "list"; items: Cell[] }
  | { kind: "text"; text: string; tone?: "ok" | "open" | "warn" | "muted" }
  | { kind: "diagram" };
type Section = { title: string; intro?: string; blocks: Block[] };
type Report = { title: string; subtitle: string; verdict: { score: number; label: string; message: string }; sections: Section[] };

const OUTPUT_STATUS: Record<Diagnosis["outputs"][number]["status"], { text: string; tone: "ok" | "warn" }> = {
  delivered: { text: "delivered", tone: "ok" },
  needs_combination: { text: "needs another method", tone: "warn" },
  unreachable: { text: "out of reach", tone: "warn" },
};
const TONE: Record<DataRow["status"], "ok" | "open" | "warn" | "muted"> = {
  in_hand: "ok", available: "open", derivable: "open", needs_component: "warn", missing: "warn", unused: "muted", initial_state: "muted",
};
const GROUP: Record<Action["group"], string> = { fix_first: "Fix first", recommended: "Recommended", optional: "Optional" };
const CHECK: Record<"ok" | "warn" | "fail", { text: string; tone: "ok" | "warn" }> = {
  ok: { text: "passed", tone: "ok" }, warn: { text: "to look at", tone: "warn" }, fail: { text: "failed", tone: "warn" },
};

const list = (items: Ref[]) => names(items) || "–";

function buildReport(result: Improvement, ctx: ReportContext): Report {
  const d = result.diagnosis;
  const s = d.study;
  const sections: Section[] = [];

  // 1. the study
  const study: [string, Cell][] = [
    ["Water challenge", s.challenge ? name(s.challenge) : "–"],
    ["Study objective", s.objective ? name(s.objective) : "–"],
  ];
  if (s.entity) study.push(["Water entity", name(s.entity)]);
  if (s.driver) study.push([s.driver_assumed ? "Driver (assumed)" : "Driver", name(s.driver)]);
  if (s.intent) study.push(["Decision intent", name(s.intent)]);
  if (s.scenario) study.push(["Scenario", name(s.scenario)]);
  if (s.output_step) study.push(["Results every", name(s.output_step)]);
  if (d.setup.software) study.push(["Software", name(d.setup.software)]);
  if (d.setup.reference_chain) study.push(["Standard workflow", name(d.setup.reference_chain)]);
  else if (d.best_template) study.push(["Compared with", `the usual workflow “${name(d.best_template)}”`]);
  sections.push({ title: "The study", blocks: [{ kind: "facts", rows: study }] });

  // 2. the verdict and the checks
  sections.push({
    title: "Verdict",
    intro: `${d.fit.blocking} to fix · ${d.fit.warnings} to improve · ${Math.round(d.coverage.primary * 100)}% of the main processes covered`,
    blocks: [
      { kind: "table", head: ["Check", "Result", "Why"],
        rows: d.checks.map((c) => [c.title, { text: CHECK[c.status].text, tone: CHECK[c.status].tone }, c.message]) },
    ],
  });

  // 3. the workflow
  const methods = d.setup.methods;
  const workflow: Block[] = [{ kind: "diagram" }];
  workflow.push({
    kind: "table", head: ["#", "Method", "Job in the workflow", "Runs in", "Gives"],
    rows: methods.map((m, i) => [
      String(i + 1),
      { text: name(m) + (m.essential ? "" : " (optional)") },
      list(m.roles),
      m.runs_in
        ? [name(m.runs_in), m.module?.name, m.module?.time_step, m.module?.resolution].filter(Boolean).join(" · ")
        : list(m.software),
      list(m.delivers),
    ]),
  });
  if (d.links.length) {
    const byId = new Map(methods.map((m) => [m.id, name(m)]));
    workflow.push({
      kind: "list",
      items: d.links.map((l) => `${byId.get(l.from) ?? l.from} → ${byId.get(l.to) ?? l.to}: ${list(l.variables)}${l.optional.length ? ` (optional: ${list(l.optional)})` : ""}`),
    });
  }
  if (d.setup.left_out.length) {
    workflow.push({ kind: "text", tone: "muted", text: `Left out on purpose: ${d.setup.left_out.map((c) => `${name(c)} (${list(c.roles)})`).join("; ")}.` });
  }
  sections.push({ title: "The workflow", intro: "Methods from upstream to downstream, and what each one passes to the next.", blocks: workflow });

  // 4. the expected outputs and how they are obtained
  if (d.outputs.length) {
    sections.push({
      title: "Expected outputs",
      blocks: d.outputs.map((o): Block[] => {
        const how = o.trace.map((t) => {
          if (t.computed_by.length) return `${name(t)}: computed by ${list(t.computed_by)}`;
          if (t.derived) return `${name(t)}: derived from ${list(t.derived.from)}${t.derived.how ? ` (${t.derived.how})` : ""}${t.derived.computed_by.length ? `, computed by ${list(t.derived.computed_by)}` : ""}`;
          if (t.derivations.length) return `${name(t)}: can be derived ${derivationText(t.derivations[0])}`;
          return `${name(t)}: not computed by this workflow`;
        });
        return [
          { kind: "facts", rows: [
            [name(o), { text: OUTPUT_STATUS[o.status].text, tone: OUTPUT_STATUS[o.status].tone }],
            ...(o.question ? [["Answers", `“${o.question}”`] as [string, Cell]] : []),
            ...(o.missing.length ? [["Missing", list(o.missing)] as [string, Cell]] : []),
          ] },
          ...(how.length ? [{ kind: "list", items: how } as Block] : []),
        ];
      }).flat(),
    });
  }

  // 5. the data, by where it comes from
  const rows = d.data.filter((r) => r.status !== "unused");
  // the source: the dataset chosen, else the open datasets that provide it (the first one linked)
  const source = (r: DataRow): Cell => {
    if (r.dataset) return { text: `${name(r.dataset)}${r.step_ref ? ` (${name(r.step_ref)})` : ""}`, href: r.dataset.url };
    if (r.status === "available" && r.datasets.length) {
      const first = r.datasets[0];
      const more = r.datasets.length - 1;
      return { text: `${name(first)}${more ? ` (+${more} more)` : ""}`, href: first.url };
    }
    return sourceOf(r);
  };
  const dataRow = (r: DataRow): Cell[] => [
    name(r),
    `${KIND[r.kind]} · ${NATURE[r.nature]}`,
    { text: STATUS[r.status].text, tone: TONE[r.status] },
    source(r),
    list(r.used_by),
  ];
  const order: DataRow["status"][] = ["missing", "needs_component", "available", "derivable", "in_hand", "initial_state"];
  sections.push({
    title: "Data required and where it comes from",
    intro: `${rows.filter((r) => r.status === "in_hand").length} in hand · ${rows.filter((r) => r.status === "available" || r.status === "derivable").length} from open data or derivable · ${rows.filter((r) => r.status === "missing" || r.status === "needs_component").length} without a source`,
    blocks: [{
      kind: "table", head: ["Data", "Use", "Status", "Source", "Used by"],
      rows: [...rows].sort((a, b) => order.indexOf(a.status) - order.indexOf(b.status)).map(dataRow),
    }],
  });

  // 6. what was changed, and what is left to do
  if (ctx.accepted.length) {
    sections.push({ title: "Changes made in the portal", blocks: [{ kind: "list", items: ctx.accepted }] });
  }
  const open = result.actions.filter((a) => !ctx.declined.includes(a.id));
  const declined = result.actions.filter((a) => ctx.declined.includes(a.id));
  if (open.length || declined.length) {
    const blocks: Block[] = [];
    if (open.length) {
      blocks.push({
        kind: "table", head: ["Priority", "Suggestion", "Effort", "Fit after"],
        rows: open.map((a) => [
          { text: GROUP[a.group], tone: a.group === "fix_first" ? "warn" : a.group === "recommended" ? "open" : "muted" },
          a.message + (a.software ? ` (${a.software.text})` : ""),
          a.effort,
          `${a.effect.fit_before} → ${a.effect.fit_after}`,
        ]),
      });
    }
    if (declined.length) blocks.push({ kind: "text", tone: "muted", text: `Declined: ${declined.map((a) => a.message).join("; ")}.` });
    sections.push({ title: "Suggested improvements", intro: "What the portal still suggests, with the fit it would give.", blocks });
  }
  if (d.warnings.length) sections.push({ title: "Notes", blocks: [{ kind: "list", items: d.warnings }] });

  return {
    title: s.challenge && s.objective ? `${name(s.challenge)} · ${name(s.objective)}` : "Workflow diagnosis",
    subtitle: d.setup.reference_chain ? name(d.setup.reference_chain) : methods.map(name).join(" → "),
    verdict: { score: d.fit.score, label: d.fit.label, message: d.fit.message },
    sections,
  };
}

// ---- Markdown --------------------------------------------------------------------------

const mdCell = (c: Cell) => {
  const text = (typeof c === "string" ? c : c.text).replace(/\|/g, "\\|").replace(/\n/g, " ");
  return typeof c !== "string" && c.href ? `[${text}](${c.href})` : text;
};

export function reportMarkdown(result: Improvement, ctx: ReportContext): string {
  const r = buildReport(result, ctx);
  const out: string[] = [
    `# ${r.title}`, "", `**Workflow:** ${r.subtitle}  `,
    `**Fit:** ${r.verdict.score}/100 (${r.verdict.label}). ${r.verdict.message}  `,
    `**Generated:** ${new Date().toLocaleString()} by the AIO Hydrology Decision Support portal  `,
    `**Reopen this study:** ${ctx.link}`, "",
  ];
  for (const section of r.sections) {
    out.push(`## ${section.title}`, "");
    if (section.intro) out.push(`_${section.intro}_`, "");
    for (const block of section.blocks) {
      if (block.kind === "facts") { out.push(...block.rows.map(([k, v]) => `- **${k}:** ${mdCell(v)}`), ""); }
      else if (block.kind === "list") { out.push(...block.items.map((i) => `- ${mdCell(i)}`), ""); }
      else if (block.kind === "text") { out.push(block.text, ""); }
      else if (block.kind === "table") {
        out.push(`| ${block.head.join(" | ")} |`, `| ${block.head.map(() => "---").join(" | ")} |`,
                 ...block.rows.map((row) => `| ${row.map(mdCell).join(" | ")} |`), "");
      }
    }
  }
  return out.join("\n");
}

// ---- the printable page ----------------------------------------------------------------

const esc = (text: string) => text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const htmlCell = (c: Cell) => {
  if (typeof c === "string") return esc(c);
  const text = esc(c.text);
  const inner = c.href ? `<a href="${esc(c.href)}">${text}</a>` : text;
  return c.tone ? `<span class="r-tone r-${c.tone}">${inner}</span>` : inner;
};

export function reportHtml(result: Improvement, ctx: ReportContext): string {
  const r = buildReport(result, ctx);
  const tone = r.verdict.label === "fit" ? "ok" : r.verdict.label === "partly fit" ? "open" : "warn";
  const body = r.sections.map((section) => `
    <section class="r-section">
      <h2>${esc(section.title)}</h2>
      ${section.intro ? `<p class="r-intro">${esc(section.intro)}</p>` : ""}
      ${section.blocks.map((block) => {
        if (block.kind === "diagram") return ctx.diagram ? `<div class="r-diagram">${ctx.diagram}</div>` : "";
        if (block.kind === "facts") return `<dl class="r-facts">${block.rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${htmlCell(v)}</dd>`).join("")}</dl>`;
        if (block.kind === "list") return `<ul class="r-list">${block.items.map((i) => `<li>${htmlCell(i)}</li>`).join("")}</ul>`;
        if (block.kind === "text") return `<p class="r-text r-${block.tone ?? "plain"}">${esc(block.text)}</p>`;
        return `<table class="r-table"><thead><tr>${block.head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead>
          <tbody>${block.rows.map((row) => `<tr>${row.map((c) => `<td>${htmlCell(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
      }).join("\n")}
    </section>`).join("\n");

  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>AIO report – ${esc(r.title)}</title>
${ctx.styles}
<style>${REPORT_CSS}</style></head>
<body class="r-body">
  <div class="r-tools"><button onclick="window.print()">Print or save as PDF</button></div>
  <main class="r-page">
    <header class="r-head">
      <div class="r-brand"><img src="${esc(new URL("/aio-logo.png", window.location.origin).href)}" alt="AIO" />
        <span>Hydrology Decision Support · workflow report</span></div>
      <h1>${esc(r.title)}</h1>
      <p class="r-sub">${esc(r.subtitle)}</p>
      <div class="r-verdict r-${tone}"><strong>${r.verdict.score}/100</strong><span>${esc(r.verdict.label)}</span><p>${esc(r.verdict.message)}</p></div>
      <p class="r-meta">Generated ${esc(new Date().toLocaleString())} · <a href="${esc(ctx.link)}">reopen this study in the portal</a></p>
    </header>
    ${body}
    <footer class="r-foot">AIO – Agir et Innover pour l'Eau · recommendations from the AIO ontology 0.9.0 (core + requirements, workflow and software extensions).
      The portal's advice supports, and does not replace, the modeller's judgement.</footer>
  </main>
</body></html>`;
}

const REPORT_CSS = `
html, body.r-body { background: #eef2f6; margin: 0; }
.r-body { font: 13px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: #14263d; }
.r-tools { position: sticky; top: 0; display: flex; justify-content: flex-end; padding: 10px 16px; background: #eef2f6; z-index: 2; }
.r-tools button { font: inherit; font-weight: 700; color: #fff; background: #1d5c9b; border: 0; border-radius: 8px; padding: 8px 16px; cursor: pointer; }
.r-page { max-width: 210mm; margin: 0 auto 24px; padding: 18mm 16mm; background: #fff; box-shadow: 0 2px 12px rgba(18,38,63,.12); box-sizing: border-box; }
.r-brand { display: flex; align-items: center; gap: 10px; color: #5b6b80; font-size: 11.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; }
.r-brand img { height: 30px; }
.r-head h1 { font-size: 22px; margin: 14px 0 2px; }
.r-sub { margin: 0 0 12px; color: #5b6b80; }
.r-verdict { display: grid; grid-template-columns: auto 1fr; gap: 0 12px; align-items: baseline; padding: 10px 14px; border-radius: 10px; border: 1px solid; }
.r-verdict strong { font-size: 22px; } .r-verdict span { font-weight: 700; text-transform: capitalize; } .r-verdict p { grid-column: 1 / -1; margin: 2px 0 0; }
.r-verdict.r-ok { background: #eef7ec; border-color: #b9dcb3; } .r-verdict.r-open { background: #eef4fb; border-color: #c7dbf0; } .r-verdict.r-warn { background: #fdf0ee; border-color: #f1c0b8; }
.r-meta { color: #5b6b80; font-size: 11.5px; margin: 8px 0 0; }
.r-meta a, .r-page a { color: #1d5c9b; }
.r-section { margin-top: 18px; break-inside: auto; }
.r-section h2 { font-size: 15px; margin: 0 0 4px; padding-bottom: 4px; border-bottom: 2px solid #1d5c9b; break-after: avoid; }
.r-intro { color: #5b6b80; margin: 4px 0 8px; }
.r-facts { display: grid; grid-template-columns: 150px 1fr; gap: 3px 12px; margin: 6px 0 8px; }
.r-facts dt { color: #5b6b80; } .r-facts dd { margin: 0; font-weight: 600; }
.r-list { margin: 4px 0 8px; padding-left: 18px; } .r-list li { margin: 2px 0; }
.r-table { width: 100%; border-collapse: collapse; margin: 6px 0 8px; font-size: 12px; }
.r-table th { text-align: left; font-size: 10.5px; text-transform: uppercase; letter-spacing: .04em; color: #5b6b80; border-bottom: 1px solid #cfd8e3; padding: 4px 6px; }
.r-table td { border-bottom: 1px solid #e6ebf1; padding: 5px 6px; vertical-align: top; }
.r-table tr { break-inside: avoid; }
.r-tone { display: inline-block; padding: 0 7px; border-radius: 999px; font-size: 11.5px; font-weight: 600; white-space: nowrap; }
.r-ok { background: #eef7ec; color: #245f24; } .r-open { background: #eaf4fd; color: #0b5c8a; } .r-warn { background: #fdf0ee; color: #a53a24; } .r-muted { color: #5b6b80; }
.r-text.r-muted { background: none; }
.r-diagram { border: 1px solid #e6ebf1; border-radius: 10px; padding: 8px; margin: 6px 0 10px; break-inside: avoid; }
.r-diagram svg { display: block; width: 100%; height: auto; max-height: 120mm; }
.r-foot { margin-top: 22px; padding-top: 8px; border-top: 1px solid #e6ebf1; color: #5b6b80; font-size: 11px; }
@media print {
  html, body.r-body { background: #fff; }
  .r-tools { display: none; }
  .r-page { box-shadow: none; padding: 0; max-width: none; }
  @page { size: A4; margin: 14mm 12mm; }
}
@media (max-width: 640px) { .r-page { padding: 16px; } .r-facts { grid-template-columns: 1fr; } }
`;

// ---- opening and saving ----------------------------------------------------------------

export function openPrintable(html: string): boolean {
  const page = window.open("", "_blank");
  if (!page) return false;      // pop-ups blocked
  page.document.open();
  page.document.write(html);
  page.document.close();
  return true;
}

export function downloadText(filename: string, text: string, type = "text/markdown") {
  const url = URL.createObjectURL(new Blob([text], { type: `${type};charset=utf-8` }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function reportFilename(result: Improvement, extension: string): string {
  const s = result.diagnosis.study;
  const words = [s.challenge ? name(s.challenge) : "workflow", s.objective ? name(s.objective) : "diagnosis"].join("-");
  const slug = words.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return `aio-report-${slug}-${new Date().toISOString().slice(0, 10)}.${extension}`;
}

// the portal's styles (dev: <style> tags; build: <link> tags), for the diagram in the report
export function portalStyles(): string {
  return [...document.querySelectorAll('style, link[rel="stylesheet"]')]
    .map((node) => node instanceof HTMLLinkElement ? `<link rel="stylesheet" href="${esc(node.href)}">` : node.outerHTML)
    .join("\n");
}
