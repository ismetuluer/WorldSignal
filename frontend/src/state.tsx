import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "./api/client";
import type { Meta, Settings, Status } from "./api/types";

interface AppState {
  settings: Settings;
  meta: Meta;
  status: Status | null;
  /** Error code while the backend is unreachable; null when healthy. */
  connectionError: string | null;
  updateSettings: (patch: Partial<Settings>) => Promise<void>;
  refreshStatus: () => void;
  refreshMeta: () => void;
}

const AppStateContext = createContext<AppState | null>(null);

const POLL_IDLE_MS = 5000;
const POLL_BUSY_MS = 1500;

function useResolvedTheme(setting: Settings["ui.theme"]): "light" | "dark" {
  const query = "(prefers-color-scheme: dark)";
  const [systemDark, setSystemDark] = useState(() => window.matchMedia?.(query).matches ?? false);
  useEffect(() => {
    const mql = window.matchMedia?.(query);
    if (!mql) return;
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);
  if (setting === "system") return systemDark ? "dark" : "light";
  return setting;
}

export function AppStateProvider({
  initialSettings,
  initialMeta,
  children,
}: {
  initialSettings: Settings;
  initialMeta: Meta;
  children: ReactNode;
}) {
  const [settings, setSettings] = useState(initialSettings);
  const [meta, setMeta] = useState(initialMeta);
  const [status, setStatus] = useState<Status | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);

  const theme = useResolvedTheme(settings["ui.theme"]);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  useEffect(() => {
    document.documentElement.lang = settings["ui.language"];
  }, [settings]);

  const poll = useCallback(async () => {
    window.clearTimeout(timer.current);
    let busy = false;
    try {
      const s = await api.status();
      setStatus(s);
      setConnectionError(null);
      busy = s.collector.busy;
    } catch (e) {
      setConnectionError(e instanceof ApiError ? e.code : "server_unreachable");
    }
    timer.current = window.setTimeout(poll, busy ? POLL_BUSY_MS : POLL_IDLE_MS);
  }, []);

  useEffect(() => {
    void poll();
    return () => window.clearTimeout(timer.current);
  }, [poll]);

  // The filter choices (languages seen so far) grow with the collection: on a fresh install they are empty at start.
  const articleTotal = status?.articles.total;
  const seenTotal = useRef(articleTotal);
  useEffect(() => {
    if (articleTotal === undefined || articleTotal === seenTotal.current) return;
    const first = seenTotal.current === undefined;
    seenTotal.current = articleTotal;
    if (!first) api.meta().then(setMeta, () => undefined);
  }, [articleTotal]);

  const updateSettings = useCallback(async (patch: Partial<Settings>) => {
    // Optimistic: theme/language switch instantly. Functional updates keep quick
    // successive changes from overwriting each other.
    let previous: Partial<Settings> = {};
    setSettings((current) => {
      previous = Object.fromEntries(Object.keys(patch).map((k) => [k, current[k as keyof Settings]]));
      return { ...current, ...patch };
    });
    try {
      const saved = await api.updateSettings(patch);
      setSettings((current) => ({ ...current, ...pick(saved, Object.keys(patch)) }));
    } catch (e) {
      setSettings((current) => ({ ...current, ...previous }));
      throw e;
    }
  }, []);

  const refreshMeta = useCallback(() => {
    api.meta().then(setMeta, () => undefined);
  }, []);

  const value: AppState = {
    settings,
    meta,
    status,
    connectionError,
    updateSettings,
    refreshStatus: () => void poll(),
    refreshMeta,
  };
  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

function pick(source: Settings, keys: string[]): Partial<Settings> {
  return Object.fromEntries(keys.map((k) => [k, source[k as keyof Settings]]));
}

export function useAppState(): AppState {
  const ctx = useContext(AppStateContext);
  if (!ctx) throw new Error("useAppState outside provider");
  return ctx;
}
