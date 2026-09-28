import { useCallback, useEffect, useRef, useState } from "react";

export type SaveStatus = "idle" | "saving" | "saved" | "error";

export const AUTOSAVE_DELAY_MS = 700;
export const RETRY_DELAY_MS = 5000;
const DRAFT_PREFIX = "worldsignal.draft.";

function readDraft(key: string): string | null {
  try {
    return localStorage.getItem(DRAFT_PREFIX + key);
  } catch {
    return null;
  }
}

function writeDraft(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(DRAFT_PREFIX + key);
    else localStorage.setItem(DRAFT_PREFIX + key, value);
  } catch {
    // Storage unavailable: the server save is still attempted and retried.
  }
}

/**
 * Text that saves itself: shortly after the user stops typing, when the component goes away and
 * when the window is closed. A failed save keeps the text on screen, reports "error" and retries
 * by itself. Only one save runs at a time; edits made during a save are saved right after it.
 *
 * Until the server has confirmed a save, the text is also kept as a local draft under
 * ``draftKey``; if the window closes while the server is unreachable, the draft comes back the
 * next time this record is opened and is saved then. Remount (React ``key``) for another record.
 */
export function useAutosave(initial: string, save: (value: string) => Promise<unknown>, draftKey: string) {
  const [recovered] = useState(() => {
    const draft = readDraft(draftKey);
    return draft !== null && draft !== initial ? draft : null;
  });
  const [value, setValueState] = useState(recovered ?? initial);
  const [status, setStatus] = useState<SaveStatus>("idle");
  const latest = useRef(recovered ?? initial);
  const saved = useRef(initial);
  const running = useRef(false);
  const timer = useRef<number | undefined>(undefined);
  const saveRef = useRef(save);
  saveRef.current = save;

  const run = useCallback(async (): Promise<void> => {
    window.clearTimeout(timer.current);
    if (running.current || latest.current === saved.current) return;
    running.current = true;
    const snapshot = latest.current;
    setStatus("saving");
    try {
      await saveRef.current(snapshot);
      saved.current = snapshot;
      running.current = false;
      if (latest.current !== saved.current) return run();
      writeDraft(draftKey, null);
      setStatus("saved");
    } catch {
      running.current = false;
      setStatus("error");
      timer.current = window.setTimeout(() => void run(), RETRY_DELAY_MS);
    }
  }, [draftKey]);

  const setValue = useCallback(
    (next: string) => {
      latest.current = next;
      setValueState(next);
      writeDraft(draftKey, next);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => void run(), AUTOSAVE_DELAY_MS);
    },
    [run, draftKey],
  );

  useEffect(() => {
    if (recovered !== null) void run(); // a draft from a previous session: save it now
    const flush = () => void run();
    window.addEventListener("pagehide", flush);
    window.addEventListener("beforeunload", flush);
    return () => {
      window.removeEventListener("pagehide", flush);
      window.removeEventListener("beforeunload", flush);
      window.clearTimeout(timer.current);
      // Leaving the page or closing the dialog: save what is pending (the draft stays until it succeeds).
      if (latest.current !== saved.current) {
        const pending = latest.current;
        void saveRef.current(pending).then(() => writeDraft(draftKey, null), () => undefined);
      }
    };
  }, [run, recovered, draftKey]);

  return { value, setValue, status, flush: run, recovered: recovered !== null };
}
