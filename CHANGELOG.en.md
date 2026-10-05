# Changelog

English version of [CHANGELOG.md](CHANGELOG.md), from 0.10.0 on. Version numbers follow
[Semantic Versioning](https://semver.org/).

## [0.17.0] — 2026-10-05 — Breaking news: instant notification and a page of its own

### Added
- **Breaking-news notification.** When a publisher labels a report "Son dakika", "BREAKING", "URGENT", "Flaş", "عاجل" and so on and **at least 3 independent sources** (adjustable: 2–5) have covered the event within the last hour, the Windows notification comes at once; it does not wait for the 10 minutes between other notifications (only 2 minutes between two breaking ones). The label is removed from the headline; clicking opens the story. The same story is not announced again as "spreading fast". Quiet hours and the notifications switch apply. Setting: Settings → System → Windows notifications → *Announce breaking news at once*.
- **Breaking page** (sidebar): labelled stories, newest first, with 3 / 12 / 24 hour windows. A red number appears on the sidebar item when there are labelled stories from the last 3 hours.
- Measured (real data, 72 hours): label + at least 3 sources gives about 4 notifications a day, 2 sources about 7; going by the number of sources alone (no label) would be dozens a day, so it was not used. (Database migration 0013.)
- **Exclusive detection widened.** The publisher's label is now also recognised as "Scoop:" at the start of a headline (Axios) and as "Exclusive:" at the start of the summary (The Guardian, The Independent: no label in the headline). On real data, 71 → 90 exclusives in the last 30 days. Most sources (NYT, WSJ, FT, Bloomberg, Al Jazeera) never put an exclusive label in their RSS; those cannot be seen this way.
- **The exclusive label is now also read from the article's page.** On the page the extension (or the plain download) fetched, the publisher's "Exclusive" / "Scoop" label is looked for: keyword and tag metas, structured data (`keywords`, `articleSection`), a small label element above the article (navigation, footer and sidebars do not count), the page title and the page description (The Guardian, The Independent). Even when a paywall leaves only the first paragraph readable the label is caught, because it is on the page. The article text is **not** searched for the word "exclusive". Phrases such as "exclusive interview" and "exclusively reported" in summaries are marked too. Verified on real Guardian and Fox News pages (no false alarm on 6 unlabelled pages); **not yet tried on NYT, FT, WSJ, Bloomberg pages**: their labels may sit elsewhere. Only pages read from now on are marked (the HTML of earlier pages is not kept). (Migration 0014: `articles.page_exclusive`.)
- **A diagnostics switch** (Settings → Full text → "Diagnostics: keep the pages that are read"). While on, the HTML of the last 40 pages read is written to `debug-pages` on this computer only, to see where a publisher puts its label and why it was not found. It never goes into backups or packages.
- **Reuters' exclusives now arrive with their own label.** Reuters keeps its site closed to automated readers, so the label is not read there; but Bing News' public RSS search returns the copies (MSN, Yahoo, U.S. News and others) that carry Reuters' own "Exclusive-" headline. The new "Reuters (Exclusive)" source runs eight searches and keeps only headlines like "Exclusive-…", "Exclusive - …" or "Reuters exclusive: …" (a new feed option, `keep_only`, migration 0015). No guessing: the label in the headline is Reuters'. One trial pass brought 39 headlines; the same story also exists unlabelled under the Reuters source, the two merge into one story and count as one independent source. Full text is fetched from the publisher's copy on request (The Print, Yahoo, BNN Bloomberg and The Star can be read; MSN cannot, open it with Go to source in the browser). Labels with the outlet in front ("CNN Exclusive: …") are recognised too.
- **An "Exclusive" search for each source.** Measured: for each of the 140 sources, searching Bing News for `"Exclusive" site:<domain>` returned headlines carrying the publisher's label for **13 sources**; those 13 (Axios, AP, Fox News, CNA, Al-Monitor, Kyiv Independent, Hindustan Times, Korea Herald, Middle East Eye, IRNA, Times of India, Global Times) got an "Exclusive" search under their real source (`keep_only: exclusive`: only what the publisher itself labelled is stored; the source name, owner and links stay the real source's). One trial pass brought 34 new labelled reports (Axios 10, CNA 5, Fox 4, AP 2…). **What cannot be done:** NYT, WSJ, FT, Bloomberg, Washington Post, the Guardian, BBC and others do not put the label in the headline, so a search cannot see it (Reuters' "Exclusive-" headline is wire style and lives on in its copies); for those the only way is reading the page (the page label above, for reports the extension reads).

## [0.16.1] — 2026-10-05 — Press a summary to open it; no extension reload needed

### Added
- **Pressing a summary on a report or story card shows all of it**, pressing again shortens it (mouse, or Enter/Space).
  Below it the Read full text, Go to source and Show original links remain.

### Changed
- **The extension's version no longer follows the program's.** The program knows which extension version it expects; the
  number rises only when the extension itself changes. The extension did not change in this release: **you do not need
  to press Reload.**

## [0.16.0] — 2026-10-05 — Single reports on the meeting list; own browser profile for the extension; automation browser removed

### Added
- **A single report can be put on the meeting list** (not only a story). Every card of the feed's "Articles" view has an
  **Add to meeting** button and the **T** key; the list shows the report with a link to its source (the "story no longer
  exists" warning is only for stories that really vanished). If the AI text arrives later, today's list follows it.
  Outputs use the same format as for stories, under the same copyright rule (AI text and link only). The full text of a
  listed report is queued too. (Database migration 0012: `meeting_items.article_id`.)
- **A browser profile of its own for the extension.** Settings → Full text → "Which browser profile does the extension run
  in?": *Own profile (recommended)* or *My browser*. In the own profile the extension and your subscription sign-ins live
  in a profile of World Signal's own; the program starts it without a window and your everyday browser, tabs and session
  are left alone. **Open own profile** opens that profile on the extensions page (you load the extension once). The default
  is still *My browser*; to switch, the extension has to be loaded into that profile once.

### Removed
- **The program's automation browser (patchright).** It was not used (not one full text came through it since the
  extension), the subscription sites refused it and it crashed the browser. Gone: that reader, the `fulltext.reader`,
  `fulltext.profile`, `fulltext.visible` settings, the "Show the browser window" and profile rows, the patchright
  dependency. The package gets about 100 MB smaller. Sources read "in the browser" are now read only by the extension.

### Measured
- Reports of the same kind of event with a changed name ("Erdoğan received X") are 0.66–0.73 similar with bge-m3 on real
  data; those above the 0.8 threshold are really the same event (two people received in the same visit). No extra merge rule
  that looks at the names was needed.

## [0.15.2] — 2026-10-02 — Holding old stories to a raised threshold

### Added
- **Settings → News collection → "Hold the last 3 days' stories to this threshold".** The merge threshold only affects new
  reports; stories built under a lower one stayed as they were (for example a mayor's visit to the President kept pulling in
  another mayor's visit the next day). **Check** says how many stories would be split, **Apply** splits them. The largest
  group keeps the story (its notes and meeting entries), the others become new stories. Stories you corrected by hand
  (detached or merged) are left alone. Nothing is split by itself.

### Fixed
- **Scrolling down the feed or the stories threw the page back to the last selected row.** Whenever the list grew (more
  loaded below, or a new story arrived) the program scrolled the selected row into view. It now does so only when a key
  (J/K) moves the selection.

## [0.15.1] — 2026-10-02 — One clear button in the search box

### Fixed
- Search boxes showed two "×" buttons once text was typed (the browser's own clear button next to ours); only ours is left.
- The extension version matches the program version; after this release press Reload on `brave://extensions`.

## [0.15.0] — 2026-10-02 — The instructions sent to the AI can be changed in the interface

### Added
- **Settings → AI instructions.** The instruction texts sent to the local (Ollama) or cloud AI with every request can now be
  changed in the interface: **Report summary** (headline, summary, category; one by one and in batches), **Story summary**
  (story headline, summary, meeting pitch, key points), **Full-text translation** and **Search words**. The default text of
  each is shown in the editor; write the style, level of detail or topics to stress to suit your own guidelines. "Back to
  default" restores the program's own text.
- **Placeholders:** `{input}` (how the material arrives), `{languages}` (output languages), `{language}` (language to
  translate into), `{fields}` (the technical description of the answer fields). The translation and search texts must
  contain the language placeholder or they are not saved; if `{fields}` or `{input}` is left out the program adds it, because
  the model cannot do the work without it.
- **What stays fixed:** the answer's JSON structure (a schema goes with every request), the check that numbers exist in the
  source, and the length limits live in the program. A change only affects work done from now on; summaries already written
  stay as they are.
- The default texts are **exactly the same** as those sent before this version (pinned by a test).
- **The layout and the amount of what is sent can be changed too.** For the report summary the pattern of each report in the
  request (`{source}`, `{language}`, `{title}`, `{text}`) can be written; for the story summary the introduction line
  (`{count}`) and the pattern of each report (`{n}` and the above). How much is sent is set by limits: characters of a
  report's text (200–60,000), characters per report in batch reading and reports per request (2–25), reports per story and
  characters of each. An empty field uses the default. More text can give a better summary but makes the work slower and, in
  the cloud, costs more. The headline must stay in the pattern.
- **Keyboard shortcuts can be changed** (Settings → Keyboard shortcuts). Each action (go to search, next / previous report,
  open, add to the meeting list) can have up to four keys: **+** adds one by pressing it, **×** removes it (the last key
  cannot be removed), "Default" restores the action. A single letter, digit or sign, or Enter, Space, the arrows, Home, End,
  PgUp, PgDn, F1–F12 can be given; a key cannot do two things (the action that owns it is named). Esc (closing windows) and
  Tab are fixed. The hint line in the feed and history and the key label in the search box show the chosen keys.
- **Font, text size and text colour can be set** (Settings → Appearance). Pick a font from the list or type the name of any font
  installed on the computer; the size scales the whole interface between 80% and 140%; the text colour is chosen separately
  for the light and the dark theme (the fainter greys are derived from the chosen colour). Each can be returned to the theme's
  own. A font name accepts only letters, digits, spaces and `, . - ' "`.
- **Settings in two columns.** Instead of one long page there are six categories on the left (General, News collection, AI,
  Full text, Archive and backup, System) and the selected category's settings on the right. The **Search settings** box
  at the top searches every category and shows only the matching settings. The last category is remembered; in a narrow
  window the list becomes a horizontal strip.

## [0.14.3] — 2026-10-02 — The extension opens no windows; old-extension warning; new icons

### Fixed
- **No window pops up while the extension reads.** When the browser was started without a window (the program found it
  closed and started it), the extension made a new minimized window for every page. Now at most one minimized window
  with an empty tab is made, and later pages are read as background tabs in it. With windows open, one that is not
  minimized is used.
- **Old extension warning.** The extension reports its version with every request. If the browser runs another (older)
  copy than the program folder's, Settings → Full text and the sidebar say "Reload the extension". After an update,
  pressing **Reload** once on the browser's extensions page is enough.

### Changed
- **Stricter story merging:** for a report to join a story, its average similarity to the story's reports must now be at
  least 0.55 (it was 0.50). A story spread over 7 days drifted from topic to topic and collected unrelated reports (e.g. an
  oil-spill report in the Gaza satellite-images story). Measured on 18,664 real reports of the last 66 hours: the largest
  story fell from 525 to 278 reports, the share of reports in 50+ stories from 13.7% to 7.6%, in-story coherence rose from
  0.60 to 0.65, and the number of real (3+ report) stories grew. The cost: in the labelled set some reports of one event
  may split into two stories. Existing stories do not change; Settings can go back to 0.50. See docs/BIRLESTIRME_KARSILASTIRMA.md.
- A README intro animation (GIF) and screenshots refreshed with the new icons.
- In the sidebar the **Feed** (newspaper) and **Meeting** (presentation board) icons are easy to tell apart.

## [0.14.2] — 2026-10-02 — The Independent's feed is fetched again

### Fixed
- **The Independent's RSS feed answered 429 ("too many requests") and could never be fetched.** The site recognised the
  way Python's HTTP client makes its connection and turned it away (the headers did not matter; the same address answered
  `curl` with 200). This feed is now fetched with the `curl.exe` that comes with Windows: no disguise, the public RSS
  address is asked for by an ordinary tool under its own name. If the site refuses that too, the feed stays failed and
  nothing else is tried. If `curl.exe` is missing the error is shown. Tried with the real feed (84 reports).

## [0.14.1] — 2026-10-02 — The extension reads in the background; reports in other scripts get the right language

### Changed
- **The extension now opens pages in a background tab** (before, each page got a minimized window of its own, which
  often came to the front). When the browser has a window open, the page is loaded in it with `active: false`, read,
  and the tab is closed; with no window open (the browser was started without one) a minimized window is used as before.
  Tried in a real Chromium with two Guardian reports: the extracted text has the same length (2468 and 5079
  characters), a second window was never open, the tabs were closed. **After the update, press "Reload" for the
  extension once on the browser's extensions page.**
- The extension texts and setup steps say "Chromium-based browser (Chrome, Brave, Edge, Opera)".

### Fixed
- **A report's language is read from the letters of its text.** The Japanese, Arabic or Russian section of a feed
  labelled English (Reuters, CNN, UNIAN, SANA ...) was shown as "English" on the card; 798 of 24,000 reports in the
  last 3 days. Now, when the text is not in Latin letters, the language comes from the letters (Japanese, Chinese,
  Korean, Arabic, Persian, Urdu, Russian, Ukrainian, Hebrew, Greek, Thai). Latin-letter texts keep the feed's label;
  a label that is already right (e.g. Ukrainian) is left alone. Existing reports are corrected once (`repair.languages`).

### Added
- Reports the extension read are summarised from their full text, ahead of the AI queue (published in 0.14.0; see there).

## [0.14.0] — 2026-10-01 — Browser extension: subscription sites are read in your own browser

### Added
- **Reports the extension read are summarised from their full text, ahead of the queue.** Even while the AI queue is
  full, a report the extension read in your own browser (exclusives, subscription sites) is summarised again from its
  full text; an earlier summary stays until the new one is ready. A full summary is written (not headline only). If
  the AI fails three times it is given up and the old summary stays. Full texts from other methods are still handled
  when the queue is empty. A story's summary is still written from its reports' summaries (not from full texts).
- **The World Signal browser extension** (the `extension` folder inside the program folder; for Chrome and Brave).
  Reports from subscription sites, especially exclusives that appear only there, are opened by **your own browser**
  instead of the program's automation browser: your real profile, your real session. The program
  decides which report is read when (the same queue, the same human pace); the extension only opens the page in a
  separate minimized window, looks at it for 3–8 seconds, scrolls down like a reader, hands the page's HTML to the
  program and closes the window. Extracting the text, detecting blocks and resting a site stay in the program. Every
  page gets a window of its own that is closed when the page is done.
- **One-time setup, three steps** (Settings → Full text → Extension): (1) in the browser's extensions page turn on
  Developer mode and choose **Load unpacked**, picking the extension folder (the **Open the extension folder** button
  shows it), (2) click the extension's icon and paste the **pairing code** from Settings, (3) be signed in to your
  subscription sites in that browser. The rest is automatic: while the browser is open (if it is closed the program can
  start it without a window; this can be switched off) the extension reads reports. If the extension stays silent
  beyond the wait the program gave it and for more than 10 minutes, the sidebar shows a one-line warning (not just
  because the program has just started or a site is having a long rest); Settings shows connected / not connected.
- **Choice of reader** (`fulltext.reader`): *Extension (recommended)* or *The program's own browser* (as before). In
  extension mode only the extension takes the jobs of "with a browser" sources; "direct download" sources are still read
  by the program. While the extension is not connected the automation browser is not used; the job waits in the queue.
- **In extension mode the new reports of paid sources are queued**; the ones the publisher calls "Exclusive" first, then
  the rest; the ones you asked for and those in your notebook still go first. The per-site daily limit and the other pace
  settings apply. Reports queued automatically that could not be read within 24 hours leave the queue (the ones you
  asked for and those in your notebook stay), so the queue does not swell.
- **A page the extension opened counts as an attempt:** if it does not open in time, does not open, cannot be read or is
  too large to take (over 8 MB), the attempt counts and the site rests for a while; after three attempts the report is
  given up. Only you closing the reading window costs no attempt. The page's HTTP status (such as 401/403/429) is passed
  to the program too, so the site is rested as with the program's own browser. Google News redirects and links that are
  not web addresses are never given to the extension. If full text is switched off or the reader is changed, the job
  the extension holds is dropped.
- **Security:** the extension talks to the program only inside this computer, on a fixed port range (47821–47830), with
  a randomly generated pairing code that is stored only on this computer (with Windows user-account encryption). A
  request from another computer, from a web page or through DNS rebinding is refused even with the code. The code can be
  replaced with **New code** (the old extension connection stops working). Before sending the code the extension checks
  that World Signal holding the same code listens on the very port it asked (a random question each time; the answer
  is signed with the code and names the port the program listens on): another program holding one of these ports
  cannot learn the code, even if it relays the question to the real program. (A program that can read the user's
  memory or files is outside this protection.) The extension opens
  no site other than the addresses the program gives it, and only `http`/`https` addresses.

### Limits and risks that do not change
- **Robot checks (CAPTCHA) and similar protections are never solved.** If such a page appears the report is marked
  "blocked" and the site is rested for longer and longer intervals. On a page the extension only scrolls; it does not
  click, type or submit forms.
- **Sites' terms of use may forbid automated reading even for subscribers.** The risk (including a warning or closing of
  your account) is yours; the pace limits can be seen and changed under Settings → Full text.
- While the browser is closed or the extension is paused no page is read; the work waits in the queue.
- The extension is not published in a browser store; when the program is updated the extension folder is updated too,
  and you press **Reload** once on the browser's extensions page.

### Removed
- The back-end code of **Add a page** (bookmark + paste: `clip.py`, `/api/clips`): the extension adds no new reports, it
  completes existing ones. Reports added earlier and the "Added by hand" source stay where they are.

### Tested
- In a real browser (Chromium, extension loaded, against a test instance) the extension paired, read two Guardian
  reports in a minimized window, and the extracted text had the same length as a plain download (3554 and 4205
  characters); the second page opened about 3 minutes after the first, and the reading window was closed afterwards.
  **Subscription sites, Brave and starting the browser without a window have not been tried yet.**

## [0.13.4] — 2026-10-01 — Key points in the meeting notes; a crashing browser no longer burns reports

### Changed
- **Meeting proposals** (screen and output): each proposal has its headline, a short summary of what happened and, as
  bullets, the **key points** (names, figures, who said what). "Why in the meeting" sentences such as "widely covered"
  are gone from the output (they stay on the story cards). Your own note appears as "My note:"; of the sources only the
  three closest to the story are listed, with links. The AI writes the key points with the story summary, from the
  reports only; figures are checked as in the summary. Stories on the meeting list go first in the queue (even if they
  were summarised before, and outside the working hours too); the screen refreshes itself when the points arrive.
  Summaries are a little longer, so each story takes the AI somewhat more time.
- The note box on the meeting list is called "Short note" instead of "Short reason".

### Removed
- **Add a page** (bookmark + paste). Adding pages one by one by hand did not fit an autonomous program; a World Signal
  extension for your own browser is being designed instead. Reports added that way stay where they are.

### Fixed
- **The browser crashed while starting and reports were marked "could not be fetched" for nothing.** The Brave opened for
  full texts crashed on start, mostly while it was updating itself (75 crash reports in its profile, each matching a
  "browser could not be started" in the log). Every crash used up an attempt of the next report, so reports failed
  without the site ever being asked, and the program tried again every minute. A browser that does not start now leaves
  the report and the site's pace untouched, is retried after 1, 2, 4 … at most 30 minutes, and its error is logged.

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
