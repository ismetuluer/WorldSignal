/** Languages offered when adding or editing a source (ISO 639-1). */
export const LANGUAGE_CHOICES = [
  "tr", "en", "ar", "ru", "uk", "fr", "de", "es", "it", "fa", "he", "zh", "ja", "ko", "az", "el", "pt", "hi", "ur",
];

export function isHttpUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return (url.protocol === "http:" || url.protocol === "https:") && url.hostname.includes(".");
  } catch {
    return false;
  }
}

/** Suggest a source name from the feed title ("BBC News - World" -> "BBC News"). */
export function suggestName(feedTitle: string | null | undefined, url: string): string {
  const title = (feedTitle ?? "").split(/\s+[-–|:]\s+/)[0]?.trim();
  if (title) return title.slice(0, 120);
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}
