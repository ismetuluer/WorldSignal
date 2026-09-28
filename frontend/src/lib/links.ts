/**
 * Google News article links (news.google.com/rss/articles/...) cannot be opened from the company network: Google
 * answers the redirect with a robot check and the browser shows "invalid address". Since 0.7.3 the catalog uses Bing
 * News, whose links are the publisher's own; articles collected before that still carry Google links, so those open
 * a web search for the exact headline instead.
 */
export function openableUrl(url: string, title: string): string {
  let host: string;
  try {
    host = new URL(url).hostname;
  } catch {
    return url;
  }
  if (host !== "news.google.com") return url;
  return `https://www.bing.com/search?q=${encodeURIComponent(`"${title}"`)}`;
}
