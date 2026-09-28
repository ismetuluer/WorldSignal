import { describe, expect, it } from "vitest";
import { openableUrl } from "../lib/links";

describe("openableUrl", () => {
  it("keeps publisher links", () => {
    expect(openableUrl("https://www.reuters.com/world/x/", "T")).toBe("https://www.reuters.com/world/x/");
    expect(openableUrl("not a url", "T")).toBe("not a url");
  });
  it("turns an old Google News link into a headline search", () => {
    const url = openableUrl("https://news.google.com/rss/articles/CBMiT0FV?oc=5", 'Erdoğan & "NATO" zirvesi');
    expect(url.startsWith("https://www.bing.com/search?q=")).toBe(true);
    expect(new URL(url).searchParams.get("q")).toBe('"Erdoğan & "NATO" zirvesi"');
  });
});
