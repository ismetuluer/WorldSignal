import type { MessageKey } from "../i18n";

const KNOWN_ERRORS = [
  "bot_check", "paywall", "not_article", "timeout", "network", "profile_in_use", "browser_failed", "no_browser",
] as const;

/** i18n key for a full-text error code (http_NNN codes share one text). */
export function fulltextErrorKey(code: string): MessageKey {
  if (code.startsWith("http_")) return "fulltext.error.http";
  const known = KNOWN_ERRORS.find((k) => k === code);
  return known ? `fulltext.error.${known}` : "fulltext.error.other";
}
