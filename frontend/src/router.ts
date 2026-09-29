import { useEffect, useState } from "react";

export const ROUTES = ["feed", "meeting", "notebook", "history", "stats", "sources", "settings"] as const;
export type Route = (typeof ROUTES)[number];

function parse(hash: string): Route {
  const name = hash.replace(/^#\/?/, "").split(/[/?]/)[0] ?? "";
  return (ROUTES as readonly string[]).includes(name) ? (name as Route) : "feed";
}

export function navigate(route: Route): void {
  window.location.hash = `/${route}`;
}

/** Minimal hash router: the desktop window has no address bar to deep-link from. */
export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parse(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parse(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

function linkedStory(hash: string): number | null {
  const query = hash.split("?")[1] ?? "";
  const id = Number(new URLSearchParams(query).get("story"));
  return Number.isInteger(id) && id > 0 ? id : null;
}

/**
 * A story named in the address (``#/feed?story=12``), e.g. from a clicked Windows notification.
 * Returns the id and a function that removes it from the address again.
 */
export function useLinkedStory(): [number | null, () => void] {
  const [id, setId] = useState<number | null>(() => linkedStory(window.location.hash));
  useEffect(() => {
    const onChange = () => setId(linkedStory(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  const clear = () => {
    window.location.hash = `/${parse(window.location.hash)}`;
  };
  return [id, clear];
}
