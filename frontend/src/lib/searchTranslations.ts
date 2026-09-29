import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useDebounced } from "./hooks";

/** "none": nothing typed; "loading"; "ok"; otherwise why there are no translations ("disabled", "gpu_busy" …). */
export type TranslationState = "none" | "loading" | "ok" | string;

export interface SearchLanguages {
  state: TranslationState;
  /** Other phrasings of the search, all languages together, without the typed words themselves. */
  phrases: string[];
}

const NONE: SearchLanguages = { state: "none", phrases: [] };
const LOADING: SearchLanguages = { state: "loading", phrases: [] };
// Each translation is a request to the AI: wait until the user has stopped typing, not for every half word.
const SETTLE_MS = 700;

// Kept for the session: going back to a search does not ask the AI again.
const cache = new Map<string, SearchLanguages>();

export function phrasesOf(q: string, queries: Record<string, string[]>): string[] {
  const seen = new Set([q.toLocaleLowerCase()]);
  const out: string[] = [];
  for (const list of Object.values(queries)) {
    for (const phrase of list) {
      const key = phrase.toLocaleLowerCase();
      if (!seen.has(key)) {
        seen.add(key);
        out.push(phrase);
      }
    }
  }
  return out;
}

/** The search in the languages the sources publish in. The typed words are searched at once; the
 * translations follow when the AI has written them (a few seconds). A result always belongs to the
 * current words: the translations of an earlier search are never sent with a new one. */
export function useSearchTranslations(q: string): SearchLanguages {
  const [answer, setAnswer] = useState<{ q: string; result: SearchLanguages } | null>(null);
  const settled = useDebounced(q, SETTLE_MS);
  const cached = q ? cache.get(q) : undefined;
  useEffect(() => {
    if (!settled || cache.has(settled)) return;
    let current = true;
    api.searchTranslations(settled).then(
      (r) => {
        const result = { state: r.state, phrases: phrasesOf(settled, r.queries) };
        if (r.state === "ok") cache.set(settled, result);
        if (current) setAnswer({ q: settled, result });
      },
      () => {
        if (current) setAnswer({ q: settled, result: { state: "unreachable", phrases: [] } });
      },
    );
    return () => {
      current = false;
    };
  }, [settled]);
  if (!q) return NONE;
  if (cached) return cached;
  return answer?.q === q ? answer.result : LOADING;
}
