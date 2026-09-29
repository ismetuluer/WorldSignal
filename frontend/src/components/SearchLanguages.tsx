import { useI18n, type MessageKey } from "../i18n";
import type { SearchLanguages } from "../lib/searchTranslations";

const SHOWN = 6;

const REASONS: Record<string, MessageKey> = {
  disabled: "search.languages.disabled",
  gpu_busy: "search.languages.busy",
};

/** Under the search box: in which other languages the search ran, or why only the typed words were searched. */
export function SearchLanguagesNote({ languages }: { languages: SearchLanguages }) {
  const { t } = useI18n();
  const { state, phrases } = languages;
  if (state === "none") return null;
  let text: string;
  if (state === "loading") text = t("search.languages.loading");
  else if (state === "ok") {
    if (!phrases.length) return null;
    const more = phrases.length - SHOWN;
    text = t("search.languages.done", { phrases: phrases.slice(0, SHOWN).join(" · ") + (more > 0 ? ` +${more}` : "") });
  } else text = t(REASONS[state] ?? "search.languages.unavailable");
  return (
    <p className="search-languages" role="status" title={state === "ok" ? phrases.join(" · ") : undefined}>
      {text}
    </p>
  );
}
