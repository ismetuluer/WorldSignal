import { describe, expect, it, vi } from "vitest";
// @ts-expect-error plain JS module outside the app
import { HELLO_TIMEOUT_MS, PORTS, call, closeOpened, findProgram, isWebUrl, readPage, readingPlan, tick } from "../../../extension/lib.js";

const json = (status: number, body: unknown) => Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });
const webcrypto = globalThis.crypto;

// What the program answers (api/extension.py hello_proof), computed here independently of lib.js.
async function proofFor(key: string, port: number, nonce: string): Promise<string> {
  const enc = new TextEncoder();
  const k = await webcrypto.subtle.importKey("raw", enc.encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = new Uint8Array(await webcrypto.subtle.sign("HMAC", k, enc.encode(`worldsignal-hello:${port}:${nonce}`)));
  return btoa(String.fromCharCode(...mac)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
const nonceOf = (url: string) => new URL(url).searchParams.get("nonce") ?? "";

/** A program on `port` holding `key`; `others` answer as World Signal with what they like. */
function programs(port: number, key: string, others: Record<number, (nonce: string) => unknown> = {}) {
  return vi.fn(async (url: string, _init?: unknown) => {
    const p = Number(new URL(url).port);
    if (p === port) return json(200, { app: "worldsignal", version: "0.14.0", proof: await proofFor(key, port, nonceOf(url)) });
    if (others[p]) return json(200, await others[p]!(nonceOf(url)));
    throw new Error("refused");
  });
}

it("the test's proof matches the program's for known vectors", async () => {
  // Same vectors as tests/test_extension_api.py (Python's hmac over the same bytes).
  expect(await proofFor("k", 47821, "0123456789abcdef")).toBe("rdSBGxEAtL9JkzpscnOm4YrFJY4-AWA6ZUk1EtgwHR4");
  expect(await proofFor("k", 47822, "0123456789abcdef")).toBe("pgxJtxNdNVZgfjaZwU_6Yt2l3QZJTXGZQOzYCfzB1hU");
});

describe("the extension", () => {
  it("finds the program on the first fixed port that proves it holds the pairing code", async () => {
    const fetch = programs(47823, "secret-code");
    expect(await findProgram(fetch, "secret-code", webcrypto)).toBe(47823);
    expect(PORTS[0]).toBe(47821);
    expect(await findProgram(() => Promise.reject(new Error("x")), "secret-code", webcrypto)).toBeNull();
    expect(await findProgram(fetch, "", webcrypto)).toBeNull(); // no code: nothing to prove, nothing sent
  });

  it("asks with a fresh random nonce each time and sends the key nowhere while looking", async () => {
    const fetch = programs(47821, "secret-code");
    await findProgram(fetch, "secret-code", webcrypto);
    await findProgram(fetch, "secret-code", webcrypto);
    const nonces = fetch.mock.calls.map(([url]) => nonceOf(url));
    expect(nonces[0]).toMatch(/^[A-Za-z0-9_-]{16,64}$/);
    expect(nonces[0]).not.toBe(nonces[1]);
    for (const [url, init] of fetch.mock.calls) {
      expect(url).not.toContain("secret-code");
      expect(JSON.stringify(init ?? {})).not.toContain("secret-code");
    }
  });

  it("rejects a program that relays the question to World Signal on another port", async () => {
    // 47821 is taken by another program; World Signal fell back to 47822. The impostor forwards the nonce there and
    // hands back the real answer, which names port 47822.
    const fetch = programs(47822, "secret-code", {
      47821: (nonce) => proofFor("secret-code", 47822, nonce).then((proof) => ({ app: "worldsignal", proof })),
    });
    expect(await findProgram(fetch, "secret-code", webcrypto)).toBe(47822);
    const asked = fetch.mock.calls.map(([url]) => Number(new URL(url).port));
    expect(asked).toEqual([47821, 47822]); // 47821 was asked first and refused
  });

  it("gives up on a port that accepts but never answers, so a round cannot stall", async () => {
    vi.useFakeTimers();
    try {
      const signals: AbortSignal[] = [];
      const fetch = vi.fn((_url: string, init?: { signal: AbortSignal }) => {
        if (init) signals.push(init.signal);
        return new Promise(() => undefined); // never settles, ignores the signal
      });
      const pending = findProgram(fetch, "secret-code", webcrypto);
      await vi.advanceTimersByTimeAsync(PORTS.length * HELLO_TIMEOUT_MS + 1000);
      expect(await pending).toBeNull();
      expect(fetch).toHaveBeenCalledTimes(PORTS.length);
      expect(signals.every((s) => s.aborted)).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it("skips an impostor on an earlier port: a wrong proof, no proof, or a replayed one", async () => {
    const wrongKey = await proofFor("another-code", 47821, "x");
    const replay = await proofFor("secret-code", 47823, "an-old-nonce-from-before");
    const fetch = programs(47825, "secret-code", {
      47821: () => ({ app: "worldsignal", proof: wrongKey }),
      47822: () => ({ app: "worldsignal", proof: null }),
      47823: () => ({ app: "worldsignal", proof: replay }),
      47824: () => ({ app: "worldsignal", proof: "not base64 !!" }),
    });
    expect(await findProgram(fetch, "secret-code", webcrypto)).toBe(47825);
  });

  it("finds nothing when no port proves itself (wrong code)", async () => {
    expect(await findProgram(programs(47821, "the-programs-code"), "a-wrong-code", webcrypto)).toBeNull();
  });

  it("asks the port found last time first", async () => {
    const fetch = programs(47828, "k");
    expect(await findProgram(fetch, "k", webcrypto, 47828)).toBe(47828);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("opens only web pages: a file:, javascript: or other address is refused and reported as load_failed", async () => {
    expect(isWebUrl("https://x.example/a")).toBe(true);
    expect(isWebUrl("http://x.example/a")).toBe(true);
    for (const bad of ["file:///C:/Windows/win.ini", "javascript:alert(1)", "chrome://settings", "data:text/html,x", "nonsense"]) {
      expect(isWebUrl(bad)).toBe(false);
      const posts: unknown[] = [];
      const read = vi.fn();
      const deps = {
        port: async () => 47821,
        key: async () => "k",
        paused: async () => false,
        call: vi.fn(async (_p: number, _k: string, path: string, body?: unknown): Promise<Record<string, unknown>> => {
          if (path === "/api/ext/next") return { lease: "L", url: bad };
          posts.push(body);
          return { status: "pending" };
        }),
        read,
      };
      expect(await tick(deps)).toBe(5);
      expect(read).not.toHaveBeenCalled();
      expect(posts).toEqual([{ lease: "L", error: "load_failed" }]);
      const chrome = fakeChrome({ html: "<p>x</p>", url: bad });
      expect((await readPage(chrome, bad, { firstLook: 0, steps: [] })).result).toEqual({ error: "load_failed" });
      expect(chrome.windows.create).not.toHaveBeenCalled();
    }
  });

  it("asks for the program only with a pairing code, and passes the code to the search", async () => {
    const port = vi.fn(async () => 47821);
    const call = vi.fn(async () => ({ wait_seconds: 60, reason: "idle" }));
    const deps = { port, key: async () => "", paused: async () => false, call, read: vi.fn() };
    expect(await tick(deps)).toBe(60);
    expect(port).not.toHaveBeenCalled();
    expect(call).not.toHaveBeenCalled();
    await tick({ ...deps, key: async () => "k" });
    expect(port).toHaveBeenCalledWith("k");
    expect(await tick({ ...deps, key: async () => "k", port: async () => null })).toBe(60);
  });

  it("sends the key and reports an unpaired extension", async () => {
    const fetch = vi.fn((_url: string, _init: { headers: Record<string, string> }) => json(401, { detail: { code: "not_paired" } }));
    await expect(call(fetch, 47821, "k", "/api/ext/next")).rejects.toThrow("not_paired");
    expect(fetch.mock.calls[0]![1].headers["X-WorldSignal-Extension"]).toBe("k");
  });

  it("reads like a person: a first look, then 4 to 9 uneven scrolls, about 20-60 seconds", () => {
    for (let seed = 0; seed < 50; seed++) {
      let x = seed / 50;
      const plan = readingPlan(() => (x = (x * 9301 + 0.49297) % 1));
      expect(plan.firstLook).toBeGreaterThanOrEqual(3000);
      expect(plan.firstLook).toBeLessThanOrEqual(8000);
      expect(plan.steps.length).toBeGreaterThanOrEqual(4);
      expect(plan.steps.length).toBeLessThanOrEqual(9);
    }
  });

  it("a plan keeps every pause in 2.5-7 s and the whole read in a person's range", () => {
    let x = 0.123;
    const random = () => (x = (x * 9301 + 0.49297) % 1);
    const totals: number[] = [];
    for (let i = 0; i < 300; i++) {
      const plan = readingPlan(random);
      for (const pause of plan.steps) {
        expect(pause).toBeGreaterThanOrEqual(2500);
        expect(pause).toBeLessThanOrEqual(7000);
      }
      const total = plan.firstLook + plan.steps.reduce((a: number, b: number) => a + b, 0);
      expect(total).toBeGreaterThanOrEqual(13000); // 3 s + 4 x 2.5 s
      expect(total).toBeLessThanOrEqual(71000); // 8 s + 9 x 7 s
      totals.push(total);
    }
    const mean = totals.reduce((a, b) => a + b, 0) / totals.length;
    expect(mean).toBeGreaterThan(20000);
    expect(mean).toBeLessThan(60000);
  });

  it("uses GET only for status; next and result are POST", async () => {
    const methods: Record<string, string> = {};
    const fetch = vi.fn((url: string, init: { method: string }) => {
      methods[url.replace(/^.*(\/api\/ext\/\w+)$/, "$1")] = init.method;
      return json(200, {});
    });
    await call(fetch, 47821, "k", "/api/ext/status");
    await call(fetch, 47821, "k", "/api/ext/next");
    await call(fetch, 47821, "k", "/api/ext/result", { lease: "L" });
    expect(methods).toEqual({ "/api/ext/status": "GET", "/api/ext/next": "POST", "/api/ext/result": "POST" });
  });

  it("tells the caller what it opened and when it is closed", async () => {
    const chrome = fakeChrome({ html: "<p>a</p>", url: "https://x.example/a" });
    const events: string[] = [];
    await readPage(chrome, "https://x.example/a", { firstLook: 0, steps: [] }, {
      onOpened: (what: { window?: number; tab?: number }) => events.push(`open ${JSON.stringify(what)}`),
      onClosed: () => events.push("closed"),
    });
    expect(events).toEqual(["open {\"window\":7}", "closed"]);
    const failing = fakeChrome({ closed: true });
    const again: string[] = [];
    await readPage(failing, "https://x.example/a", { firstLook: 0, steps: [] }, {
      onOpened: (what: { window?: number; tab?: number }) => again.push(`open ${JSON.stringify(what)}`),
      onClosed: () => again.push("closed"),
    });
    expect(again).toEqual(["open {\"window\":7}", "closed"]);
  });

  it("gives up with timeout when the page never finishes loading, and closes the window", async () => {
    vi.useFakeTimers();
    try {
      const chrome = fakeChrome({ loading: true, url: "https://x.example/a" });
      const pending = readPage(chrome, "https://x.example/a", { firstLook: 0, steps: [] });
      await vi.advanceTimersByTimeAsync(50000);
      expect((await pending).result).toEqual({ error: "timeout" });
      expect(chrome.windows.remove).toHaveBeenCalledWith(7);
      expect(chrome.scripting.executeScript).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("reports script_failed when the page hands back nothing", async () => {
    const chrome = fakeChrome({ url: "https://x.example/a" }); // no html
    const out = await readPage(chrome, "https://x.example/a", { firstLook: 0, steps: [] });
    expect(out.result).toEqual({ error: "script_failed" });
    expect(chrome.windows.remove).toHaveBeenCalledWith(7);
    const empty = fakeChrome({ html: "", url: "https://x.example/a" });
    expect((await readPage(empty, "https://x.example/a", { firstLook: 0, steps: [] })).result).toEqual({ error: "script_failed" });
  });

  it("opens the page in a background tab of a window that is already open, and closes only that tab", async () => {
    const chrome = fakeChrome({ html: "<html>report</html>", url: "https://x.example/a", hosts: [{ id: 5, focused: false }, { id: 9, focused: true }] });
    const events: string[] = [];
    const out = await readPage(chrome, "https://x.example/a", { firstLook: 0, steps: [0] }, {
      onOpened: (what: { window?: number; tab?: number }) => events.push(`open ${JSON.stringify(what)}`),
      onClosed: () => events.push("closed"),
    });
    expect(chrome.tabs.create).toHaveBeenCalledWith({ windowId: 9, url: "https://x.example/a", active: false });
    expect(chrome.windows.create).not.toHaveBeenCalled();
    expect(out.result).toEqual({ html: "<html>report</html>", final_url: "https://x.example/a" });
    expect(chrome.tabs.remove).toHaveBeenCalledWith(3);
    expect(chrome.windows.remove).not.toHaveBeenCalled();
    expect(events).toEqual(["open {\"tab\":3}", "closed"]);
  });

  it("closes the background tab even when the page could not be read", async () => {
    const chrome = fakeChrome({ closed: true, hosts: [{ id: 5, focused: true }] });
    expect((await readPage(chrome, "https://x.example/a", { firstLook: 0, steps: [] })).result).toEqual({ error: "tab_closed" });
    expect(chrome.tabs.remove).toHaveBeenCalledWith(3);
  });

  it("closeOpened closes what the stopped worker left, tab or window", async () => {
    const chrome = fakeChrome({});
    await closeOpened(chrome, { tab: 11 });
    await closeOpened(chrome, { window: 12 });
    await closeOpened(chrome, null);
    expect(chrome.tabs.remove).toHaveBeenCalledWith(11);
    expect(chrome.windows.remove).toHaveBeenCalledWith(12);
  });

  it("without any open window the page gets a minimized window of its own, reads it and closes the window", async () => {
    const chrome = fakeChrome({ html: "<html>report</html>", url: "https://x.example/a" });
    const out = await readPage(chrome, "https://x.example/a", { firstLook: 0, steps: [0, 0, 0, 0] });
    expect(chrome.windows.create).toHaveBeenCalledWith(expect.objectContaining({ url: "https://x.example/a", state: "minimized", focused: false }));
    expect(out.result).toEqual({ html: "<html>report</html>", final_url: "https://x.example/a" });
    expect(chrome.windows.remove).toHaveBeenCalledWith(7);
  });

  it("closes the window even when the page could not be read", async () => {
    const chrome = fakeChrome({ closed: true });
    await readPage(chrome, "https://x.example/a", { firstLook: 0, steps: [] });
    expect(chrome.windows.remove).toHaveBeenCalledWith(7);
  });

  it("says the tab was closed instead of failing", async () => {
    const chrome = fakeChrome({ closed: true });
    const out = await readPage(chrome, "https://x.example/a", { firstLook: 0, steps: [] });
    expect(out.result).toEqual({ error: "tab_closed" });
  });

  it("one tick: asks for a job, reads it, posts the result, waits as told otherwise", async () => {
    const posts: unknown[] = [];
    const deps = {
      port: async () => 47821,
      key: async () => "k",
      paused: async () => false,
      call: vi.fn(async (_p: number, _k: string, path: string, body?: unknown): Promise<Record<string, unknown>> => {
        if (path === "/api/ext/next") return { lease: "L", url: "https://x.example/a" };
        posts.push(body);
        return { status: "done" };
      }),
      read: async () => ({ result: { html: "<p>t</p>", final_url: "https://x.example/a" } }),
    };
    expect(await tick(deps)).toBe(5);
    expect(posts).toEqual([{ lease: "L", html: "<p>t</p>", final_url: "https://x.example/a" }]);
    deps.call = vi.fn(async () => ({ wait_seconds: 300, reason: "resting" }));
    expect(await tick(deps)).toBe(300);
    expect(await tick({ ...deps, paused: async () => true })).toBe(60);
  });

  it("hands the page's HTTP status back with the page, and the tick posts it", async () => {
    const chrome = fakeChrome({ html: "<p>Forbidden</p>", url: "https://x.example/a", status: 403 });
    const out = await readPage(chrome, "https://x.example/a", { firstLook: 0, steps: [] });
    expect(out.result).toEqual({ html: "<p>Forbidden</p>", final_url: "https://x.example/a", status: 403 });
    const posts: unknown[] = [];
    const deps = {
      port: async () => 47821,
      key: async () => "k",
      paused: async () => false,
      call: vi.fn(async (_p: number, _k: string, path: string, body?: unknown): Promise<Record<string, unknown>> => {
        if (path === "/api/ext/next") return { lease: "L", url: "https://x.example/a" };
        posts.push(body);
        return { status: "failed" };
      }),
      read: async () => out,
    };
    await tick(deps);
    expect(posts).toEqual([{ lease: "L", html: "<p>Forbidden</p>", final_url: "https://x.example/a", status: 403 }]);
  });

  it("reads the status from the page's navigation entry, null when the browser does not say", async () => {
    const plan = { firstLook: 0, steps: [] };
    const chrome = fakeChrome({ html: "<p>x</p>", url: "https://x.example/a" });
    await readPage(chrome, "https://x.example/a", plan);
    const calls = chrome.scripting.executeScript.mock.calls as unknown as [[{ func: (p: typeof plan) => Promise<{ status: number | null }> }]];
    const inPage = calls[0][0].func;
    const entries = vi.spyOn(performance, "getEntriesByType");
    try {
      entries.mockReturnValue([{ responseStatus: 429 } as unknown as PerformanceEntry]);
      expect((await inPage(plan)).status).toBe(429);
      entries.mockReturnValue([{ responseStatus: 0 } as unknown as PerformanceEntry]);
      expect((await inPage(plan)).status).toBeNull();
      entries.mockReturnValue([]);
      expect((await inPage(plan)).status).toBeNull();
    } finally {
      entries.mockRestore();
    }
  });

  it("a failed read is posted as an error, not as a page", async () => {
    const posts: unknown[] = [];
    const deps = {
      port: async () => 47821,
      key: async () => "k",
      paused: async () => false,
      call: vi.fn(async (_p: number, _k: string, path: string, body?: unknown): Promise<Record<string, unknown>> => {
        if (path === "/api/ext/next") return { lease: "L", url: "https://x.example/a" };
        posts.push(body);
        return { status: "done" };
      }),
      read: async () => ({ result: { error: "timeout" } }),
    };
    expect(await tick(deps)).toBe(5);
    expect(posts).toEqual([{ lease: "L", error: "timeout" }]);
  });
});

function fakeChrome(page: { html?: string; url?: string; closed?: boolean; loading?: boolean; status?: number; hosts?: { id: number; focused: boolean }[] }) {
  return {
    windows: {
      create: vi.fn(async () => ({ id: 7, tabs: [{ id: 3 }] })),
      remove: vi.fn(async () => undefined),
      getAll: vi.fn(async () => page.hosts ?? []),
    },
    tabs: {
      create: vi.fn(async () => ({ id: 3 })),
      remove: vi.fn(async () => undefined),
      get: vi.fn(async () => (page.closed ? Promise.reject(new Error("No tab")) : { id: 3, status: page.loading ? "loading" : "complete", url: page.url })),
    },
    scripting: {
      executeScript: vi.fn(async (_opts: unknown) => [
        { result: page.status === undefined ? { html: page.html, final_url: page.url } : { html: page.html, final_url: page.url, status: page.status } },
      ]),
    },
  };
}
