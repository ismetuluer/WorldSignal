import { useMemo } from "react";
import { useAppState } from "../state";

/** The actions that have a key. Escape (closes search and dialogs) and Tab (moves the focus) stay fixed. */
export const ACTIONS = ["search", "next", "prev", "open", "meeting"] as const;
export type ShortcutAction = (typeof ACTIONS)[number];
export type ShortcutMap = Record<ShortcutAction, string[]>;

export const DEFAULT_SHORTCUTS: ShortcutMap = {
  search: ["/"],
  next: ["j"],
  prev: ["k"],
  open: ["enter", "o"],
  meeting: ["t"],
};
export const MAX_KEYS = 4;
const RESERVED = new Set(["escape", "tab"]);
// The keys the program accepts besides single characters (the server checks the same list).
const NAMED = /^(space|enter|arrow(up|down|left|right)|home|end|page(up|down)|f([1-9]|1[0-2]))$/;

/** A key event as the setting names it: lower-case, "space" for the space bar; null for a lone modifier. */
export function keyOf(e: Pick<KeyboardEvent, "key">): string | null {
  const key = e.key === " " ? "space" : e.key.toLowerCase();
  if (["shift", "control", "alt", "meta", "capslock", "altgraph", "dead", "unidentified"].includes(key)) return null;
  return key;
}

/** True when the key can be given to an action (a single character or one of the named keys, not a reserved one). */
export function isAssignable(key: string | null): key is string {
  return key !== null && !RESERVED.has(key) && ([...key].length === 1 || NAMED.test(key));
}

/** What to show on a key cap. */
export function keyLabel(key: string): string {
  const named: Record<string, string> = {
    enter: "Enter", space: "Space", arrowup: "↑", arrowdown: "↓", arrowleft: "←", arrowright: "→",
    home: "Home", end: "End", pageup: "PgUp", pagedown: "PgDn",
  };
  return named[key] ?? (NAMED.test(key) ? key.toUpperCase() : key.length === 1 ? key.toUpperCase() : key);
}

/** The keys in force: the user's, and the default for every action they have not changed. */
export function resolveShortcuts(custom: Record<string, string[]> | undefined): ShortcutMap {
  const out = {} as ShortcutMap;
  for (const action of ACTIONS) {
    const keys = custom?.[action];
    out[action] = keys && keys.length ? keys : DEFAULT_SHORTCUTS[action];
  }
  return out;
}

/** The values for the one-line hint under the feed's title ("J / K navigate · Enter open ..."): the first key of each. */
export function hintKeys(map: ShortcutMap): Record<"next" | "prev" | "open" | "meeting" | "search", string> {
  const first = (a: ShortcutAction) => keyLabel(map[a][0] ?? "?");
  return { next: first("next"), prev: first("prev"), open: first("open"), meeting: first("meeting"), search: first("search") };
}

export function useShortcuts(): ShortcutMap {
  const { settings } = useAppState();
  const custom = settings["ui.shortcuts"];
  return useMemo(() => resolveShortcuts(custom), [custom]);
}

/** The action that already uses `key`, other than `except` (a key can only do one thing). */
export function takenBy(map: ShortcutMap, key: string, except: ShortcutAction): ShortcutAction | null {
  return ACTIONS.find((a) => a !== except && map[a].includes(key)) ?? null;
}
