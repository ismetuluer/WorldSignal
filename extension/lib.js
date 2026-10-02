// World Signal extension: everything that can be tested without a browser. background.js wires it to chrome.*.
// The extension only ever opens http(s) URLs the program hands it and does nothing on a page except scroll and read
// its HTML: it never clicks, types, submits forms or touches a robot check (such a page is returned as it is and the
// program pauses the site).
export const PORTS = Array.from({ length: 10 }, (_, i) => 47821 + i);
const LOAD_TIMEOUT_MS = 45000;
const HELLO_PREFIX = "worldsignal-hello:";
export const HELLO_TIMEOUT_MS = 5000;

const base64url = (bytes) =>
  btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

function fromBase64url(text) {
  if (typeof text !== "string" || !/^[A-Za-z0-9_-]+$/.test(text)) return null;
  try {
    const plain = atob(text.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (text.length % 4)) % 4));
    return Uint8Array.from(plain, (c) => c.charCodeAt(0));
  } catch {
    return null;
  }
}

// Constant time: the comparison does not stop at the first byte that differs.
function sameBytes(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}

export function newNonce(crypto = globalThis.crypto) {
  return base64url(crypto.getRandomValues(new Uint8Array(24)));
}

// HMAC-SHA256(key, "worldsignal-hello:" + port + ":" + nonce): only the program that holds the pairing code can compute
// it, and it names the port that program listens on.
export async function helloProof(key, port, nonce, crypto = globalThis.crypto) {
  const enc = new TextEncoder();
  const hmacKey = await crypto.subtle.importKey("raw", enc.encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", hmacKey, enc.encode(`${HELLO_PREFIX}${port}:${nonce}`)));
}

// `work(signal)` with a time limit: aborted (and given up) when it takes longer than `ms`.
function withTimeout(work, ms) {
  const controller = new AbortController();
  let timer;
  const expired = new Promise((_, reject) => {
    timer = setTimeout(() => {
      controller.abort();
      reject(new Error("timeout"));
    }, ms);
  });
  return Promise.race([work(controller.signal), expired]).finally(() => clearTimeout(timer));
}

// Does World Signal, holding this pairing code, listen on this very port? A fresh nonce per probe, so an old answer
// cannot be replayed, and the proof names the program's own port, so another program on this port that relays the
// question to World Signal (listening elsewhere) gets an answer that does not fit. A listener that never answers is
// given up after HELLO_TIMEOUT_MS.
export async function proves(fetch, port, key, crypto = globalThis.crypto) {
  try {
    const nonce = newNonce(crypto);
    const body = await withTimeout(async (signal) => {
      const r = await fetch(`http://127.0.0.1:${port}/api/ext/hello?nonce=${nonce}`, { signal });
      return r.ok ? r.json() : null;
    }, HELLO_TIMEOUT_MS);
    if (!body || body.app !== "worldsignal") return false;
    const given = fromBase64url(body.proof);
    return given !== null && sameBytes(given, await helloProof(key, port, nonce, crypto));
  } catch {
    return false; // not there, not World Signal, or no answer in time
  }
}

// The first port where World Signal proves it holds the pairing code (`preferred`, the port found last time, is tried
// first). The key is sent nowhere else: another program listening on one of these ports learns nothing.
export async function findProgram(fetch, key, crypto = globalThis.crypto, preferred = null) {
  if (!key) return null;
  const order = preferred == null ? PORTS : [preferred, ...PORTS.filter((p) => p !== preferred)];
  for (const port of order) {
    if (await proves(fetch, port, key, crypto)) return port;
  }
  return null;
}

// Only web pages are ever opened: never file:, javascript:, chrome: or other addresses.
export function isWebUrl(url) {
  try {
    const { protocol } = new URL(url);
    return protocol === "http:" || protocol === "https:";
  } catch {
    return false;
  }
}

// The only read-only endpoint; every other one (next, result) is a POST.
export const GET_PATHS = new Set(["/api/ext/status"]);

export async function call(fetch, port, key, path, body) {
  const r = await fetch(`http://127.0.0.1:${port}${path}`, {
    method: GET_PATHS.has(path) ? "GET" : "POST",
    headers: { "Content-Type": "application/json", "X-WorldSignal-Extension": key },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (r.status === 401) throw new Error("not_paired");
  if (!r.ok) throw new Error(`http_${r.status}`);
  return r.json();
}

const between = (random, low, high) => low + random() * (high - low);

export function readingPlan(random = Math.random) {
  const steps = Math.floor(between(random, 4, 10));
  return {
    firstLook: Math.round(between(random, 3000, 8000)),
    steps: Array.from({ length: steps }, () => Math.round(between(random, 2500, 7000))),
  };
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Runs inside the article page: look, scroll down in uneven steps like a reader, then hand back the page.
function readInPage(plan) {
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  return (async () => {
    await wait(plan.firstLook);
    for (const pause of plan.steps) {
      window.scrollBy(0, 250 + Math.floor(Math.random() * 450));
      await wait(pause);
    }
    // The page's HTTP status (401/403/429 ...) tells the program to rest the site even without a robot-check text.
    const nav = performance.getEntriesByType("navigation")[0];
    const status = nav && typeof nav.responseStatus === "number" && nav.responseStatus > 0 ? nav.responseStatus : null;
    return { html: document.documentElement.outerHTML, final_url: location.href, status };
  })();
}

async function loaded(chrome, tabId) {
  const until = Date.now() + LOAD_TIMEOUT_MS;
  while (Date.now() < until) {
    const tab = await chrome.tabs.get(tabId);
    if (tab.status === "complete") return true;
    await sleep(500);
  }
  return false;
}

// Opens the page where it disturbs nobody: a background tab in a browser window that is already open (no window
// appears, nothing takes focus). Only when the browser has no normal window (started without one) a minimized window
// of its own is made. Returns what to close afterwards: {tab} or {window}.
async function open(chrome, url) {
  const hosts = (await chrome.windows.getAll({ windowTypes: ["normal"] }).catch(() => [])) || [];
  const host = hosts.find((w) => w.focused) || hosts[0];
  if (host && host.id != null) {
    const tab = await chrome.tabs.create({ windowId: host.id, url, active: false });
    return { tabId: tab.id, close: { tab: tab.id } };
  }
  const win = await chrome.windows.create({ url, state: "minimized", focused: false });
  const tabId = win.tabs && win.tabs[0] ? win.tabs[0].id : null;
  return { tabId, close: { window: win.id } };
}

// One page, one background tab of its own that is closed afterwards (a service worker can be stopped by the
// browser between pages, so nothing is kept for reuse: nothing is left behind). If the worker itself is stopped
// mid-read, `finally` never runs: `onOpened({tab} | {window})` lets the caller remember what was opened (outside
// lib.js, which stays free of chrome.storage) so a later round can close what was left; `onClosed()` says it is gone.
export async function readPage(chrome, url, plan, hooks = {}) {
  if (!isWebUrl(url)) return { result: { error: "load_failed" } };
  let opened = null;
  try {
    opened = await open(chrome, url);
    if (hooks.onOpened) await hooks.onOpened(opened.close);
    const tabId = opened.tabId;
    if (tabId == null) return { result: { error: "load_failed" } };
    if (!(await loaded(chrome, tabId))) return { result: { error: "timeout" } };
    const [frame] = await chrome.scripting.executeScript({ target: { tabId }, func: readInPage, args: [plan] });
    if (!frame || !frame.result || !frame.result.html) return { result: { error: "script_failed" } };
    return { result: frame.result };
  } catch (e) {
    const closed = /No tab|closed|No window/i.test(String(e && e.message));
    return { result: { error: closed ? "tab_closed" : "load_failed" } };
  } finally {
    if (opened) {
      await closeOpened(chrome, opened.close);
      if (hooks.onClosed) await hooks.onClosed();
    }
  }
}

export async function closeOpened(chrome, close) {
  if (close && close.tab != null) await chrome.tabs.remove(close.tab).catch(() => undefined);
  else if (close && close.window != null) await chrome.windows.remove(close.window).catch(() => undefined);
}

// One round: returns how many seconds to wait before the next one. `deps.port(key)` finds the program that proves it
// holds the key (findProgram); the key is sent only there.
export async function tick(deps) {
  if (await deps.paused()) return 60;
  const key = await deps.key();
  if (!key) return 60;
  const port = await deps.port(key);
  if (port == null) return 60;
  const job = await deps.call(port, key, "/api/ext/next");
  if (!job.lease) return job.wait_seconds ?? 60;
  if (!isWebUrl(job.url)) {
    await deps.call(port, key, "/api/ext/result", { lease: job.lease, error: "load_failed" });
    return 5;
  }
  const { result } = await deps.read(job.url);
  await deps.call(port, key, "/api/ext/result", { lease: job.lease, ...result });
  return 5;
}
