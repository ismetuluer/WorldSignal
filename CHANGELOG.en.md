# Changelog

English version of [CHANGELOG.md](CHANGELOG.md), from 0.10.0 on. Version numbers follow
[Semantic Versioning](https://semver.org/).

## [0.11.2] — 2026-09-29 — Downloaded zip and "What's new" fix

### Fixed
- **The app did not start when extracted from a zip downloaded from the internet** ("Failed to resolve
  Python.Runtime.Loader.Initialize"). Windows marks every file extracted from a downloaded zip as "from the internet",
  and .NET then refused to load the libraries that draw the window (Python.Runtime, WebView2). The new
  `WorldSignal.exe.config` in the package lets them load like local files; no package is made without it.
- **In "What's new", sentences broke off in the middle of the line**, and marks such as `###` and `**` were shown. The
  release notes now appear with headings, bullets and bold text, and the lines flow with the window width.
- Reports marked "(Exclusive)" at the **end** of the headline (Trend News Agency's style) did not get the
  **Exclusive** badge.

## [0.11.1] — 2026-09-28 — Update fix

### Fixed
- **Updating from the app failed with "the program folder is in use".** When World Signal was started from File
  Explorer, the program folder was its current directory, and the new program started by the updater inherited it.
  Windows cannot rename a folder that a running program uses as its current directory, so the update could not
  replace the program and put the old version back. The new program now leaves the folder first; the running program
  and its browser windows no longer hold it either. The updater also waits up to a minute (instead of 20 seconds) for
  the old program's windows to close.
- The release notes are published in Turkish and English; "What's new" shows the part in the interface language.

## [0.11.0] — 2026-09-28 — Summary languages and cloud AI

### Added
- **You choose the summary languages.** Settings → Artificial intelligence → **Summary languages**: 1–4 of 31
  languages (for example Portuguese and Arabic). Headlines, summaries, story pitches and full-text translations are
  written in them. The language button on the cards switches between them, and outputs can be made in any of them.
  Right-to-left languages (Arabic, Persian, Hebrew) are shown in the right direction. A language added later is filled
  in for older articles in the background. Default: the interface language plus English.
- **Cloud AI.** Instead of Ollama, you can use **Google Gemini**, an **OpenAI-compatible** service (OpenAI,
  OpenRouter, Groq, Mistral, DeepSeek…, or LM Studio on your computer) or **Anthropic Claude** with your own API key.
  The connection test lists the service's models. Requests per minute can be set; above the limit the app waits.
  - The key is kept only on this computer, encrypted with Windows encryption tied to your account (DPAPI). It never
    appears on screen, in logs or in backups.
  - Settings warn clearly that article texts, including full texts read with your subscriptions, are sent to the
    chosen service. Its terms, cost and copyright are your responsibility.
  - Story merging still runs in Ollama (`bge-m3`) on your computer.
- **My country → Topics** can be added and removed, and you can write your own (up to 20). The AI says whether a
  report is about one of them.

### Changed
- The prompts no longer assume a Turkish newsroom. The "does it mention Türkiye?" question is asked only for users in
  Türkiye. The rating method is unchanged: the AI reads the report and fixed rules decide.
- Plainer interface texts: document paths and internal notes were removed, and country and language texts now suit
  users from any country. The timeline's "first Turkish source" became the first source in the interface language.
- AI texts are stored by language in one JSON column (schema v9). Existing Turkish and English results were carried
  over unchanged.

### Fixed
- **The language filter stayed empty** ("No match"): on a fresh install its choices were loaded only at start-up. They
  now refresh as articles arrive.
- `http://localhost:11434` in the Ollama address box was wrongly shown as invalid.

## [0.10.0] — 2026-09-28 — Sites without RSS

### Added
- **News sitemaps are read as feeds.** Many news sites without RSS publish a "news sitemap" for search engines, with
  headline, time and language. World Signal reads it like RSS, but only if the site's robots.txt allows it (asked once
  a day per site). If robots.txt cannot be read, the sitemap is not read. Plain sitemaps without headlines are not
  used, since every page would have to be opened.
- **Add source finds feeds from a site's address.** If you type the site's address instead of an RSS address, the
  RSS/Atom links the page declares and the news sitemaps robots.txt allows are suggested; **Test** tries one.
- In the catalogue, CNN, Times of Israel, Kathimerini and Bloomberg HT now also take their reports straight from the
  publisher's sitemap. The Bing feed stays for the summaries, and the same report is kept once.

### Tried and not used
- The news sitemaps of AP and Al Arabiya refuse automated readers (403). Reuters' robots.txt closes automated reading
  completely. The Telegraph allows its sitemap in robots.txt but blocks automated readers in other ways. These sites
  are still followed through Bing.
- RSS-Bridge was not added. It needs a PHP server, and its Reuters bridge is blocked too. The sitemap approach covers
  its useful part without any installation.
