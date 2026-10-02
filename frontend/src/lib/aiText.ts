/**
 * Which AI text to show. The AI writes every text in the user's languages (setting "ai.languages"); the UI
 * shows the requested language (at first the interface language) and the others are a click away. A text the
 * AI has not written in that language falls back to another AI language, then to the original.
 */
import type { AiText, AiTexts, Article, MeetingItem, Settings, Story } from "../api/types";

/** A language code the AI writes in ("tr", "pt", …). */
export type AiLang = string;

/** The languages the AI writes in: the setting, or the interface language and English. */
export function aiLanguages(settings: Pick<Settings, "ai.languages" | "ui.language">): string[] {
  const chosen = settings["ai.languages"];
  if (chosen && chosen.length) return chosen;
  return [...new Set([settings["ui.language"], "en"])];
}

/** The AI languages this text exists in, in the order of the user's languages. */
export function languagesOf(texts: AiTexts | null | undefined, order: string[] = []): string[] {
  const have = Object.keys(texts ?? {}).filter((l) => texts?.[l]?.title);
  return [...order.filter((l) => have.includes(l)), ...have.filter((l) => !order.includes(l))];
}

function pick(texts: AiTexts | null | undefined, lang: AiLang): { lang: string; text: AiText } | null {
  if (!texts) return null;
  const own = texts[lang];
  if (own?.title) return { lang, text: own };
  const other = Object.keys(texts).find((l) => texts[l]?.title);
  return other ? { lang: other, text: texts[other]! } : null;
}

export interface ShownText {
  text: string;
  /** Language the text is in: an AI language, or the article's own language for an original. */
  lang: string;
  translated: boolean;
}

export function articleTitle(a: Article, lang: AiLang): ShownText {
  const p = a.ai_status === "done" ? pick(a.ai_texts, lang) : null;
  return p ? { text: p.text.title, lang: p.lang, translated: true } : { text: a.title, lang: a.language, translated: false };
}

export function articleSummary(a: Article, lang: AiLang): string {
  return (a.ai_status === "done" && pick(a.ai_texts, lang)?.text.summary) || a.summary;
}

export function storyTitle(s: Story, lang: AiLang): ShownText {
  const own = s.ai_status === "done" ? pick(s.ai_texts, lang) : null;
  if (own) return { text: own.text.title, lang: own.lang, translated: true };
  const rep = s.representative;
  const repAi = rep ? pick(rep.ai_texts, lang) : null;
  if (repAi) return { text: repAi.text.title, lang: repAi.lang, translated: true };
  return { text: rep?.title ?? "", lang: rep?.language ?? "und", translated: false };
}

export function storySummaryText(s: Story, lang: AiLang): string {
  const rep = s.representative;
  return (
    (s.ai_status === "done" && pick(s.ai_texts, lang)?.text.summary) ||
    (rep && pick(rep.ai_texts, lang)?.text.summary) ||
    rep?.summary ||
    ""
  );
}

export function storyWhy(s: Story, lang: AiLang): string | null {
  return (s.ai_status === "done" && pick(s.ai_texts, lang)?.text.why) || null;
}

export function storyConflict(s: Story, lang: AiLang): string | null {
  return (s.ai_status === "done" && pick(s.ai_texts, lang)?.text.conflict) || null;
}

function pointList(points: string | undefined): string[] {
  return (points ?? "").split("\n").map((p) => p.trim()).filter(Boolean);
}

export function storyPoints(s: Story, lang: AiLang): string[] {
  return s.ai_status === "done" ? pointList(pick(s.ai_texts, lang)?.text.points) : [];
}

/** The AI languages a story can be shown in (its own texts, else its representative report's). */
export function storyLanguages(s: Story, order: string[] = []): string[] {
  const own = s.ai_status === "done" ? languagesOf(s.ai_texts, order) : [];
  return own.length ? own : languagesOf(s.representative?.ai_texts, order);
}

export function meetingText(item: MeetingItem, lang: AiLang) {
  const p = pick(item.texts, lang);
  return {
    title: p?.text.title || item.title,
    summary: p?.text.summary || null,
    why: p?.text.why || null,
    points: pointList(p?.text.points),
    /** The story is still there but its summary has no key points yet (the AI writes them first). */
    pointsPending: item.story_id !== null && p?.text.points === undefined,
  };
}
