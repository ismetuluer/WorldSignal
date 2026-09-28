/**
 * Which AI language to show. Every AI text exists in Turkish and English (prompt v5); the UI
 * shows the interface language and the other one is a click away. Texts written before English
 * existed fall back to the other AI language, then to the original.
 */
import type { Article, MeetingItem, Story } from "../api/types";

export type AiLang = "tr" | "en";

export const otherLang = (l: AiLang): AiLang => (l === "tr" ? "en" : "tr");

function pick<T>(lang: AiLang, tr: T | null | undefined, en: T | null | undefined): T | null {
  const first = lang === "tr" ? tr : en;
  const second = lang === "tr" ? en : tr;
  return first || second || null;
}

export interface ShownText {
  text: string;
  /** Language the text is in: an AI language, or the article's own language for an original. */
  lang: string;
  translated: boolean;
}

export function articleTitle(a: Article, lang: AiLang): ShownText {
  if (a.ai_status === "done") {
    const t = pick(lang, a.title_tr, a.title_en);
    if (t) return { text: t, lang: t === (lang === "tr" ? a.title_tr : a.title_en) ? lang : otherLang(lang), translated: true };
  }
  return { text: a.title, lang: a.language, translated: false };
}

export function articleSummary(a: Article, lang: AiLang): string {
  return (a.ai_status === "done" && pick(lang, a.summary_tr, a.summary_en)) || a.summary;
}

export function storyTitle(s: Story, lang: AiLang): ShownText {
  const done = s.ai_status === "done";
  const own = done ? pick(lang, s.ai_title_tr, s.ai_title_en) : null;
  if (own) return { text: own, lang: own === (lang === "tr" ? s.ai_title_tr : s.ai_title_en) ? lang : otherLang(lang), translated: true };
  const rep = s.representative;
  const repAi = rep ? pick(lang, rep.title_tr, rep.title_en) : null;
  if (repAi) return { text: repAi, lang: repAi === (lang === "tr" ? rep!.title_tr : rep!.title_en) ? lang : otherLang(lang), translated: true };
  return { text: rep?.title ?? "", lang: rep?.language ?? "und", translated: false };
}

export function storySummaryText(s: Story, lang: AiLang): string {
  const done = s.ai_status === "done";
  const rep = s.representative;
  return (done && pick(lang, s.ai_summary_tr, s.ai_summary_en)) || (rep && pick(lang, rep.summary_tr, rep.summary_en)) || rep?.summary || "";
}

export function storyWhy(s: Story, lang: AiLang): string | null {
  return s.ai_status === "done" ? pick(lang, s.ai_why, s.ai_why_en) : null;
}

export function meetingText(item: MeetingItem, lang: AiLang) {
  return {
    title: pick(lang, item.title, item.title_en) ?? item.title,
    summary: pick(lang, item.summary, item.summary_en),
    why: pick(lang, item.why, item.why_en),
  };
}
