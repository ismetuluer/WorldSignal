import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, initToken, setToken } from "../api/client";
import { isHttpUrl, suggestName } from "../pages/sourceForm";

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
  window.history.replaceState(null, "", "/");
});

describe("initToken", () => {
  it("moves the token from the URL to session storage", () => {
    window.history.replaceState(null, "", "/?t=secret#/sources");
    expect(initToken()).toBe("secret");
    expect(window.location.search).toBe("");
    expect(window.location.hash).toBe("#/sources");
    expect(initToken()).toBe("secret");
  });
});

describe("api requests", () => {
  it("sends the token and encodes array parameters", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], next: null, total: 0 })));
    vi.stubGlobal("fetch", fetchMock);
    setToken("tok");
    await api.articles({ hours: 24, region: ["turkey", "europe"], q: "İstanbul", source: [] });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/articles?hours=24&region=turkey&region=europe&q=%C4%B0stanbul");
    expect((init.headers as Record<string, string>)["X-WorldSignal-Token"]).toBe("tok");
  });

  it("turns error payloads into ApiError codes", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { code: "feed_exists" } }), { status: 409 })));
    await expect(api.sources()).rejects.toMatchObject({ code: "feed_exists", status: 409 });

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: [{ msg: "bad" }] }), { status: 422 })));
    await expect(api.sources()).rejects.toMatchObject({ code: "validation" });

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>", { status: 502 })));
    await expect(api.sources()).rejects.toMatchObject({ code: "http_502" });

    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const err = await api.sources().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("server_unreachable");
  });

  it("handles 204 responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(api.deleteSource(1)).resolves.toBeUndefined();
  });
});

describe("source form helpers", () => {
  it("validates web addresses", () => {
    expect(isHttpUrl("https://www.aa.com.tr/rss")).toBe(true);
    expect(isHttpUrl("http://example.com/feed")).toBe(true);
    expect(isHttpUrl("ftp://example.com")).toBe(false);
    expect(isHttpUrl("javascript:alert(1)")).toBe(false);
    expect(isHttpUrl("haber sitesi")).toBe(false);
    expect(isHttpUrl("https://localhost")).toBe(false);
  });

  it("suggests a name from the feed title or host", () => {
    expect(suggestName("BBC News - World", "https://feeds.bbci.co.uk/x")).toBe("BBC News");
    expect(suggestName("", "https://www.example.com/rss")).toBe("example.com");
    expect(suggestName(null, "not a url")).toBe("");
  });
});
