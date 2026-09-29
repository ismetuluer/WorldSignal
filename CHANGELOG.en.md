# Changelog

English version of [CHANGELOG.md](CHANGELOG.md), from 0.10.0 on. Version numbers follow
[Semantic Versioning](https://semver.org/).

## [0.13.3] — 2026-09-29 — Add a page, first to report, and outlets that disagree

### Added
- **Add a page** (Feed → Add a page): for sites that do not let programs in, such as The Economist and WSJ. You read the
  report in your own browser with your subscription and click the **Copy to World Signal** button you dragged to the
  bookmarks bar once (the page is copied to the clipboard); back in the program you paste it and press **Add**. The
  report enters under the site's source (or "Added by hand") with its full text; the AI writes the summary, it joins
  stories, can be searched and added to the notebook. No request is sent to the site and no protection is bypassed:
  you opened the page. Sending the same page again refreshes its text. If the page has no report or no full text, the
  reason is given.
- **"First to report"**: on the card and in the detail of a story covered by several outlets, the outlet that published
  the event first and when (by publication time). For stories spread over several days it shows the first report of the
  chain; the time is written out, so it does not mislead.
- **"Outlets disagree"**: when writing the story summary the AI names, in one sentence with the outlets' names, a fact on
  which outlets contradict each other (a figure, who did what, who is responsible); it shows as an orange note on the
  card. It stays empty when the outlets agree or the model is not sure. New summaries carry it; older ones do not.

## [0.13.2] — 2026-09-29 — Clicking a report opens its full text

### Changed
- **Clicking a report opens its full text:** on a report card of the feed and in the story detail, the headline opens
  the reader inside the program instead of the source site. If the text is not there yet, the reader asks for it, shows
  the summary meanwhile and switches to the text when it arrives; if it cannot be read, it says why. Without a
  translation the original text opens, the translation one click away. With full texts switched off (Settings → Full
  text) the headline opens the source as before.
- A **Go to source** button on the cards, on every report in the story detail and in the reader.

### Fixed
- **The hour boxes of working hours and quiet hours were squeezed and showed "0" instead of "07".**
- **The full-text reader opened from a card of the feed stayed behind the other cards and could not be read.** Dialogs
  are now drawn on the page itself instead of inside the card, so they always open on top (a bug of the full-text
  button in the feed, added in 0.13.1).

## [0.13.1] — 2026-09-29 — "My country" really switches off, working hours, fixes

### Added
- **Working hours** (Settings → Background). Default: it works day and night, so you can leave the program open all the
  time. You can pick a time window; outside it collecting news, the AI and full texts rest. What you ask for by hand
  (Summarise, fetch the full text, Scan now) is still done; the window and your data stay usable.
- **Country labels are a separate option** (Settings → My country → Country labels, on by default). When off, changing
  the country or topics does not rate older reports again and cards show no label.

- **Full text in the feed:** a **Fetch full text** / **Read full text** button on story cards and on report cards. It
  follows the state without reloading the card ("Full text queued…") and opens the reader when the text arrives (for
  your own reading only; never in outputs). On a story card the button is for the story's representative report; the
  other reports are in the story detail.
- **Translate the full text too** (Settings → Full text, off by default = the summary only). When on, every full text
  that arrives is also translated into your summary languages (a lot of AI work); when off, press **Translate** in the
  reader.

### Changed
- **"Outside my region" replaces "Global" in the region filter:** reports of every source outside the local region
  (Türkiye). To separate the wire agencies (Reuters, AP, AFP, Bloomberg) use Source group → Agencies. The choice is
  offered only to users whose country is Türkiye (other countries have no "local region" defined).
- **With "My country" off the AI no longer does that work at all:** the country and topic questions are left out of
  the report and story prompts (shorter prompts and answers, faster work), and summaries are no longer written again
  because "the country facts are missing". Cost: reports processed while it is off have no country facts; if you
  switch it on later it applies to new reports only.
- **The breaking-news indicator** is now a blinking red dot (the old one looked like a wireless network icon).
- **Sites that refuse us are treated more carefully:** after a bot check or a 401/403/429 the pause doubles each time
  the same refusal repeats within three days (up to 72 hours), and sites asking for a login (401) are paused too. The
  aim is that subscriptions are not flagged as suspicious.

### Fixed
- **Broken Turkish letters in some feeds, such as TRT Haber** ("SoykÄ±rÄ±m"): UTF-8 text that was read as Windows-1252
  is repaired when new reports are read; the 69 stored reports were repaired once (search index included).

## [0.13.0] — 2026-09-29 — The AI keeps up, the database gets smaller

### Added
- **How much the AI writes** (Settings → Artificial intelligence). About 7,500 reports arrive a day and the app is
  open about 8 hours a day. At ~8 seconds per report the AI could read at most ~4,000 reports a day, so its queue
  never caught up. There are three options:
  - **Every report** (as before), for strong computers or a fast cloud service.
  - **Stories together**: reports of an event covered by several sources are not read separately; the story summary
    covers them. The story summary now also extracts the facts for your country (which countries, whether Türkiye
    is mentioned, your topics). The story's link to your country comes from its reports and from these facts, with
    the same rules. Recent summaries written without these facts are written once more.
  - **Fast** (default): single reports are also read ten at a time for their headline, category and link to your
    country. The summary is written with the **Summarise** button on the report. Measured on real news: ~3.3 instead
    of ~8 seconds per report, and all 30 of 30 reports were usable. The daily work drops from ~65,000 to ~12,000
    seconds.

- **Two new source groups in the feed:** the "Source group" filter offers **Exclusives** (reports the publisher marks
  "Exclusive", "Özel haber" …) and **Articles (opinion, analysis, columns)**. An article is recognised by the site's
  own section in its address (`/opinion/`, `/commentisfree/`, `/yazarlar/` …) or by a label in the headline
  ("Opinion:", "Analysis |", "… - opinion"). They come from every source; the source list does not change. In the
  real feed over the last 24 hours: 7 exclusives, 76 articles.

### Changed
- **The ranking opens up to the world:** at most 6 independent sources count from one region, and the sources part of
  the score is full at 40 sources instead of 12. Before, a domestic story in 12 outlets of one country's press got the
  same sources score as a world story in 57 foreign outlets. Measured on the real feed (last 24 hours): among the top
  20 stories, those mostly covered by Turkish outlets dropped from 11 to 4, and the stories with the most foreign
  sources rose from 28th, 36th and 53rd to 2nd, 4th and 8th. Big domestic stories stay near the top. The "N sources"
  label on the card still counts every source.
- **"My country" is optional** (Settings → My country → Use my country). When it is off, the link to your country
  does not count in the importance score, and the feed hides the country filter and the country labels on cards.
  The AI keeps extracting the countries, so switching it back on takes effect at once.
- **Backups are five times smaller.** A backup is now a compressed `.zip` without the story-merging vectors, which
  are computed again within minutes after a restore. Measured: 80 MB → ~15 MB. Old `.db` backups are still listed
  and can be restored.
- **Vectors at half size, kept 4 days.** Story merging looks at the last 72 hours, so vectors are kept 4 days
  instead of 7, and stored as 16-bit numbers (measured: only 4 of 27,122 similar pairs change their decision). The
  largest part of the database (~210 MB) drops to ~60 MB.
- **The space of removed data goes back to the disk:** maintenance compacts the database once free space passes 20%
  of the file.

## [0.12.0] — 2026-09-29 — Search in other languages, and Statistics

### Added
- **Statistics** (a new "Statistics" page). Choose the period at the top: 24 hours (hour by hour), or 7 or 30 days
  (day by day).
  - **Headline numbers:** reports, stories and independent sources (one media group counts once), with the change
    against the previous period of equal length.
  - **Topic trend:** type a topic to see in how many reports and from how many sources it appears per hour or day,
    and its share of all reports. It is also searched in your sources' languages, like the new search below. Without
    a topic, all reports are shown.
  - **Share of the news:** by category (only reports whose category is known; that share is stated) and by the
    region of the reporting press, with the change in percentage points against the previous period.
  - **Rising:** the stories that grew fastest in the last 6 hours (last 24 hours for 7 days, last 72 hours for 30
    days). Click one to open it.
  - **Sources:** reports, stories and latest report per source; sources with no reports in the period are shown too.
  - **Countries mentioned most**, from the reports the AI has read (their number is stated).
  - Every chart can also be shown as a table, and hovering or keyboard focus shows the values. While collection does
    not cover the previous period, the page says there is not enough history to compare, instead of showing
    misleading changes.
- **Search also runs in the languages your sources publish in.** Most foreign reports have no summary in your
  language (the AI cannot keep up with every report), so a search in your language did not find them. For example,
  WSJ's "North Korea Is Testing Swarm Attacks Mixing Drones and Missiles" did not come up for "kuzey kore iha".
  The words you type are now searched at once. Then the AI translates them into the languages of the enabled sources
  ("North Korea drone", "Северная Корея беспилотник", "Nordkorea Drohne" …), and those reports are added to the list.
  This works in the Feed and in History. The line under the search box shows the translations used, or why there
  are none (the AI is off, another model is on the graphics card…). Measured on this computer: "kuzey kore" finds 140
  reports instead of 14, "seçim" (election) 574 instead of 118, and "ateşkes" (ceasefire) 178 instead of 60.
- The translation is requested once you stop typing and is remembered for the session. With Ollama it takes a few
  seconds, and up to 20 seconds while the graphics card is busy with summaries.
- With a cloud AI service, the search words are sent to that service too. The warning in Settings says so.

### Changed
- **Subscription sites moved to the Sources page**, unchanged, below the paid sources. Settings → Full text has a
  button that leads there.
- **Subscription sites are read like a person would, more slowly**, so that bot protection is not triggered. On sites
  read in the browser there are now at least 20 minutes between two pages of one site (3 minutes for pages you ask
  for) and at most 15 pages per site per day. No pages are opened by themselves between 00:00 and 07:00; the ones you
  ask for are still fetched. Each page is first looked at for a few seconds, then scrolled down in uneven steps
  (20-60 seconds), and only then is its text taken. The pause between pages went from 25-60 seconds to 1-3 minutes.
  Change these under Settings → Full text → **Reading pace on subscription sites** and **Rest at night on
  subscription sites**. CAPTCHAs are still never solved.

### Tried and not used
- **Semantic search** (with bge-m3 from story merging): in the measurements, short Turkish searches found no foreign
  reports. They ranked same-language headlines and section names such as "United Nations" or "Flash" first. It only
  helped with long, descriptive searches, and it could only cover the last 7 days.

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
