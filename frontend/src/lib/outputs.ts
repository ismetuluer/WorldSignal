/**
 * The four output templates: meeting proposals, story details, morning bulletin
 * by category, selected notebook entries. Each produces
 *   - ``html``: a fragment with inline styles, so it pastes cleanly into Word and Outlook and
 *     also prints well (wrapped by ``printDocument``);
 *   - ``text``: plain text for WhatsApp and similar (``*bold*`` titles).
 *
 * Every template can be made in any of the user's AI languages: the AI texts of that language are used and
 * the labels come from the matching interface dictionary (English for languages without one; the caller passes
 * an ``I18n`` for it).
 *
 * Copyright: only AI text, headlines, source names and links are ever included — never the
 * publishers' own summaries or full text.
 */
import type { MeetingItem, Story } from "../api/types";
import type { I18n, MessageKey } from "../i18n";
import { meetingText, storyPoints, storySummaryText, storyTitle, storyWhy, type AiLang } from "./aiText";
import { textDirection } from "./hooks";
import { openableUrl } from "./links";

export interface OutputDoc {
  title: string;
  html: string;
  text: string;
}

/** A story as it appears in an output. */
export interface Entry {
  title: string;
  summary: string | null;
  why: string | null;
  /** Key names, figures and statements (stories summarised since 0.13.4). */
  points: string[];
  category: string | null;
  sources: { name: string; url: string | null }[];
  sourceCount: number;
}

const MAX_LINKS = 8;
/** The meeting list names only the closest few sources (the snapshot puts them first). */
const MEETING_LINKS = 3;
const FONT = "'Segoe UI', Calibri, Arial, sans-serif";
const MUTED = "#6e6e73";

export function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** Only http(s) links are written into outputs. */
function safeUrl(url: string | null): string | null {
  return url && /^https?:\/\//i.test(url) ? url : null;
}

export function entryFromStory(s: Story, lang: AiLang = "tr"): Entry {
  const title = storyTitle(s, lang).text;
  // Only AI text as summary: storySummaryText falls back to the publisher's own summary, which never goes out.
  const summary = storySummaryText(s, lang);
  const aiSummary = summary && summary !== s.representative?.summary ? summary : null;
  const firstUrl = new Map<string, string>();
  for (const m of [...s.members].sort((a, b) => a.sort_at.localeCompare(b.sort_at))) {
    if (!firstUrl.has(m.source_name)) firstUrl.set(m.source_name, openableUrl(m.url, m.title));
  }
  const names = s.sources.length ? s.sources : [...firstUrl.keys()];
  return {
    title,
    summary: aiSummary,
    why: storyWhy(s, lang),
    points: storyPoints(s, lang),
    category: s.category,
    sources: names.map((name) => ({ name, url: firstUrl.get(name) ?? null })),
    sourceCount: s.source_count,
  };
}

export function entryFromMeetingItem(item: MeetingItem, lang: AiLang = "tr"): Entry {
  const text = meetingText(item, lang);
  return {
    title: text.title,
    summary: text.summary,
    why: text.why,
    points: text.points,
    category: item.category,
    sources: item.sources,
    sourceCount: item.sources.length,
  };
}

function longDate(i18n: I18n, day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Intl.DateTimeFormat(i18n.locale, { dateStyle: "full" }).format(new Date(y!, m! - 1, d!));
}

function header(title: string, subtitle: string): { html: string; text: string } {
  return {
    html:
      `<h1 style="font-family:${FONT};font-size:18pt;font-weight:700;margin:0 0 2pt;color:#1d1d1f">${escapeHtml(title)}</h1>` +
      `<p style="font-family:${FONT};font-size:9.5pt;color:${MUTED};margin:0 0 14pt">${escapeHtml(subtitle)}</p>`,
    text: `*${title}*\n${subtitle}\n`,
  };
}

function sourcesLine(i18n: I18n, e: Entry, max = MAX_LINKS): { html: string; text: string } {
  if (e.sources.length === 0) return { html: "", text: "" };
  const shown = e.sources.slice(0, max);
  const more = e.sources.length - shown.length;
  const label = i18n.t("output.sources");
  const html = shown
    .map((s) => {
      const url = safeUrl(s.url);
      return url
        ? `<a href="${escapeHtml(url)}" style="color:#0066cc;text-decoration:none">${escapeHtml(s.name)}</a>`
        : escapeHtml(s.name);
    })
    .join(", ");
  const text = shown.map((s) => (safeUrl(s.url) ? `${s.name} (${s.url})` : s.name)).join("\n  ");
  return {
    html: `<p style="font-family:${FONT};font-size:9.5pt;color:${MUTED};margin:3pt 0 0">${escapeHtml(label)}: ${html}${more > 0 ? ` +${more}` : ""}</p>`,
    text: `${label}:\n  ${text}${more > 0 ? `\n  +${more}` : ""}`,
  };
}

function para(text: string, style = ""): string {
  return `<p style="font-family:${FONT};font-size:11pt;margin:3pt 0 0;${style}">${escapeHtml(text).replace(/\n/g, "<br>")}</p>`;
}

function entryBlock(
  i18n: I18n,
  e: Entry,
  opts: { number?: number; reason?: string | null; note?: string | null; summary?: boolean; points?: boolean; links?: number },
) {
  const prefix = opts.number !== undefined ? `${opts.number}. ` : "";
  const src = sourcesLine(i18n, e, opts.links);
  let html = `<div style="margin:0 0 12pt;page-break-inside:avoid">`;
  html += `<p style="font-family:${FONT};font-size:12pt;font-weight:700;margin:0">${escapeHtml(prefix + e.title)}</p>`;
  let text = `*${prefix}${e.title}*`;
  if (opts.reason) {
    html += para(opts.reason);
    text += `\n${opts.reason}`;
  }
  if (opts.summary) {
    const summary = e.summary ?? i18n.t("output.noSummary");
    html += para(summary, e.summary ? "" : `color:${MUTED};font-style:italic`);
    text += `\n${summary}`;
  }
  if (opts.points && e.points.length) {
    html += `<ul style="font-family:${FONT};font-size:11pt;margin:4pt 0 0;padding-left:16pt">` +
      e.points.map((p) => `<li style="margin:1pt 0">${escapeHtml(p)}</li>`).join("") + "</ul>";
    text += e.points.map((p) => `\n• ${p}`).join("");
  }
  if (opts.note) {
    html += `<p style="font-family:${FONT};font-size:11pt;margin:5pt 0 0;padding:4pt 8pt;border-left:3px solid #0071e3;background:#f2f7fd">` +
      `<b>${escapeHtml(i18n.t("output.note"))}:</b> ${escapeHtml(opts.note).replace(/\n/g, "<br>")}</p>`;
    text += `\n${i18n.t("output.note")}: ${opts.note}`;
  }
  html += src.html + "</div>";
  if (src.text) text += `\n${src.text}`;
  return { html, text };
}

function wrap(title: string, parts: { html: string; text: string }[]): OutputDoc {
  return {
    title,
    html: `<div style="font-family:${FONT};color:#1d1d1f;line-height:1.45">${parts.map((p) => p.html).join("")}</div>`,
    text: parts.map((p) => p.text).join("\n\n").trim() + "\n",
  };
}

/** 1. Meeting proposals: numbered headline, what happened (the summary), the key names, figures and statements as
 * bullets, the user's own note, and the closest few sources. Why the AI found it worth the meeting is left out: it
 * says nothing the presenter can use. */
export function meetingOutput(i18n: I18n, day: string, items: MeetingItem[], lang: AiLang = "tr"): OutputDoc {
  const title = i18n.t("output.title.meeting");
  const parts = [header(title, longDate(i18n, day))];
  items.forEach((item, i) => {
    const e = entryFromMeetingItem(item, lang);
    parts.push(entryBlock(i18n, e, { number: i + 1, summary: !!e.summary, points: true, note: item.comment || null, links: MEETING_LINKS }));
  });
  return wrap(title, parts);
}

/** 2. Story details: headline, Turkish summary, source names with links. */
export function storyOutput(i18n: I18n, story: Story, day: string, lang: AiLang = "tr"): OutputDoc {
  const title = i18n.t("output.title.story");
  const e = entryFromStory(story, lang);
  return wrap(title, [
    header(title, `${longDate(i18n, day)} · ${i18n.plural("output.sourceCount", e.sourceCount)}`),
    entryBlock(i18n, e, { summary: true }),
  ]);
}

/** 3. Morning bulletin: the most important stories grouped by category (categories by their best story). */
export function bulletinOutput(i18n: I18n, day: string, hours: number, stories: Story[], lang: AiLang = "tr"): OutputDoc {
  const title = i18n.t("output.title.bulletin");
  const groups = new Map<string, Entry[]>();
  for (const s of stories) {
    const e = entryFromStory(s, lang);
    const key = e.category ?? "";
    groups.set(key, [...(groups.get(key) ?? []), e]);
  }
  const parts = [header(title, `${longDate(i18n, day)} · ${i18n.t("bulletin.range", { n: hours })}`)];
  // Categories in the order of their most important story; uncategorised ("Other") last.
  const ordered = [...groups].sort(([a], [b]) => Number(a === "") - Number(b === ""));
  for (const [category, entries] of ordered) {
    const name = category ? i18n.t(`category.${category}` as MessageKey) : i18n.t("output.uncategorized");
    parts.push({
      html: `<h2 style="font-family:${FONT};font-size:13pt;font-weight:700;color:#0071e3;margin:14pt 0 6pt;border-bottom:1px solid #d2d2d7;padding-bottom:2pt">${escapeHtml(name)}</h2>`,
      text: `— ${name.toLocaleUpperCase(i18n.locale)} —`,
    });
    for (const e of entries) parts.push(entryBlock(i18n, e, { summary: true }));
  }
  return wrap(title, parts);
}

/** 4. Selected notebook entries, each with the user's note. */
export function notesOutput(i18n: I18n, day: string, notes: { title: string; body: string; entry: Entry | null }[]): OutputDoc {
  const title = i18n.t("output.title.notes");
  const parts = [header(title, longDate(i18n, day))];
  for (const n of notes) {
    const e: Entry = n.entry ?? { title: n.title, summary: null, why: null, points: [], category: null, sources: [], sourceCount: 0 };
    parts.push(entryBlock(i18n, { ...e, title: e.title || n.title }, { summary: !!n.entry, note: n.body }));
  }
  return wrap(title, parts);
}

/** Full printable page around an output (A4, generous margins, date line at the bottom). */
export function printDocument(doc: OutputDoc, footer: string, lang: string): string {
  return `<!doctype html><html lang="${escapeHtml(lang)}" dir="${textDirection(lang)}"><head><meta charset="utf-8"><base target="_blank"><title>${escapeHtml(doc.title)}</title>
<style>
  @page { size: A4; margin: 18mm 16mm 20mm; }
  html { background: #fff; }
  body { margin: 24px; font-family: ${FONT}; color: #1d1d1f; }
  a { color: #0066cc; }
  footer { margin-top: 18pt; padding-top: 6pt; border-top: 1px solid #d2d2d7; font-size: 8.5pt; color: ${MUTED}; }
  @media print { body { margin: 0; } }
</style></head><body>${doc.html}<footer>${escapeHtml(footer)}</footer></body></html>`;
}
