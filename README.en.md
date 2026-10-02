# World Signal

**[Türkçe](README.md) · English**

**A Windows desktop app that gathers the world's news on one screen, merges reports of the same event, ranks them by
importance and summarises them in the languages you choose.**

<p align="center"><img src="docs/showreel.gif" alt="World Signal intro animation" width="720"></p>

It was built to prepare the morning editorial meeting in a newsroom. It scans the RSS feeds of hundreds of sources all
day and gathers reports of the same event into one "story" card ("in 9 sources"). It then ranks the stories by
importance and, if you wish, uses AI to write headlines and summaries in the languages you pick, for example English and
Portuguese. It also has a meeting list, a notebook, past days and printable outputs.

---

## Screenshots

These are real screens of the program (with data from public news feeds).

<p align="center"><img src="docs/screenshots/feed-en.png" alt="Feed: story cards in order of importance" width="860"></p>

**Feed.** Reports of the same event on one card, in order of importance. The labels under each card say why the score
is high ("43 sources", "3 sources in 3 h", "Türkiye link"); "First to report" names the outlet that published first.

<p align="center"><img src="docs/screenshots/story-en.png" alt="Story detail: summary, score breakdown, notes" width="760"></p>

**Story detail.** The summary, how the score was calculated, day-by-day development, all reports and your notes.

<p align="center"><img src="docs/screenshots/meeting-en.png" alt="Meeting list" width="760"></p>

**Meeting list.** Add stories in one click, drag to reorder, write a short note on each suggestion. Under each
proposal the key points the AI took from the reports (names, figures, statements) are listed as bullets, in the output
too.

<p align="center"><img src="docs/screenshots/stats-en.png" alt="Statistics: topic trend" width="860"></p>

**Statistics.** The trace of a topic hour by hour and its share of the news, category and region shares, rising stories.

<p align="center"><img src="docs/screenshots/sources-en.png" alt="Sources" width="860"></p>

**Sources.** Switch sources on and off, add your own RSS address; feeds that do not work are shown with the reason.

<p align="center"><img src="docs/screenshots/feed-dark-en.png" alt="Dark theme" width="860"></p>

**Dark theme.** Light, dark, or following Windows.

---

## Contents

- [Screenshots](#screenshots)
- [What it does](#what-it-does)
- [Installation](#installation)
- [Updates](#updates)
- [Artificial intelligence (optional)](#artificial-intelligence-optional)
  - [Summary languages](#summary-languages) · [Cloud AI](#cloud-ai)
- [Using it](#using-it)
- [Subscription sites: the browser extension](#subscription-sites-the-browser-extension)
- [Copyright and subscriptions](#copyright-and-subscriptions)
- [Privacy and security](#privacy-and-security)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

---

## What it does

| | |
|---|---|
| **News gathering** | About 140 sources come ready: Western press, agencies, Middle East, Russia/Ukraine, Asia, Europe, Turkish press and sports. Every feed enters the catalogue only after it was tested and worked. You can add your own RSS addresses. |
| **Stories** | Reports of the same event are merged into one card, even across languages. You can split off a wrongly merged report or merge two stories. |
| **Importance** | The ranking weighs independent sources, freshness, **links to your country** and your own interests. Every card says **why** its score is high. Reports the publisher marks as "Exclusive" get a badge, and so do fast-spreading **Breaking** stories. |
| **Summaries** | In 1–4 languages you choose, the AI writes a headline, a 3–5 sentence summary, a category and a "why it matters" line. It can run in Ollama on your computer or in a cloud service with your own key. Summaries rely only on the source text, and the original headline and link are always one click away. |
| **Meeting and notes** | Add a story to the meeting list with one key, reorder it by dragging, add notes to stories and keep a notebook by day. |
| **Outputs** | Meeting list, story detail, morning briefing and notes. Copy formatted (Word/Outlook), copy plain text (WhatsApp), print/PDF or **send by e-mail**. |
| **History** | Pick a day in the calendar to see that morning's ranking, search all days, and follow a story day by day. |
| **Statistics** | A topic hour by hour or day by day and its share of the news, the spread over categories and regions, rising stories, and counts per source and country. |
| **Full text** | Read and translate whole articles inside the app, from open sites and from sites **you subscribe to**; subscription sites can be read by [an extension](#subscription-sites-the-browser-extension) in your own browser. |
| **In the background** | The app keeps scanning from the system tray after the window closes. If an important story spreads fast, it sends a Windows notification. |

## Installation

**Requirements:** Windows 10 or 11 (64-bit). No installer, administrator rights or other software is needed. Microsoft
Edge WebView2 ships with Windows.

1. Download the newest `WorldSignal-<version>-windows.zip` from the [Releases](../../releases/latest) page.
2. Right-click the zip → **Extract All**. Choose **a writable folder on your own computer**, e.g.
   `Documents\WorldSignal`.
   - Protected folders such as `Program Files` and network folders are **not recommended**. The app runs from them but
     cannot update itself.
3. Double-click **`WorldSignal.exe`** in the extracted `WorldSignal` folder.
   - On the first start Windows may say "Windows protected your PC". This is normal because the app is not signed.
     Choose **More info → Run anyway**. The warning appears only once.
   - Some antivirus programs (e.g. Trend Micro) also stop an unknown program on its first start and ask. If you trust
     it, allow it.
4. To add a desktop shortcut, right-click `WorldSignal.exe` → **Show more options → Send to → Desktop (create shortcut)**.

On the first start the sources are scanned at once. Articles appear within seconds and stories within minutes.

**Your data** (database, notes, settings, backups, logs) is never kept in the program folder but always in
`%LOCALAPPDATA%\WorldSignal` (Settings → Data → **Open folder**). Deleting or updating the program folder does not
touch your data. The database is backed up automatically every day (a compressed `.zip`; the story-merging vectors,
which can be computed again, are left out, so a backup is about a fifth of the database). The space of removed data is
given back to the disk during maintenance.

## Updates

The app finds new versions by itself:

1. Shortly after start-up and every 6 hours, it checks the latest release on this page.
2. If there is a new version, it downloads it in the background and verifies the file with its **SHA-256 checksum**.
3. A **"World Signal x.y.z is ready — Restart and update"** bar appears at the top. **What's new** shows what changed
   in that version.
4. When you press the button, the app closes, replaces its folder with the new version and starts again. If something
   goes wrong, the old version is put back and you are told so.

Under Settings → **Updates** you can turn off automatic checking or downloading, or press **Check now**. An app
running from a network folder or a read-only folder cannot update itself. In that case, download the new zip from this
page and extract it over the old folder; your data stays in place.

## Artificial intelligence (optional)

World Signal also works without AI: articles are gathered, listed in their original language, searched and noted.
The AI does two jobs:

| Feature | Where it runs | Hardware |
|---|---|---|
| **Story merging** (finding reports of the same event) | Always in [Ollama](https://ollama.com) on your computer, model `bge-m3` (1.2 GB) | No graphics card needed; runs on the processor. |
| **Headlines and summaries** | A language model in Ollama **or** a cloud service (see [Cloud AI](#cloud-ai)) | For Ollama a strong graphics card is recommended; a cloud service needs none. |

Ollama is free and needs no administrator rights. **With Ollama everything runs on your computer and no text leaves
it.**

### Setting up Ollama

1. Install Ollama from [ollama.com/download](https://ollama.com/download).
2. Open a Command Prompt and download the story-merging model:
   ```
   ollama pull bge-m3
   ```
3. If your graphics card can handle it, also download a language model and choose it in World Signal under
   **Settings → Artificial intelligence → Model**:

   | Graphics memory | Recommended model | Note |
   |---|---|---|
   | 16 GB or more | Gemma 4 26B-A4B | Best results in our tests |
   | 8–12 GB | `gemma4:12b` or `qwen3.5:9b` | Good, faster |
   | 6–8 GB | `gemma4` (8B) | Acceptable; short summaries |
   | No dedicated graphics card | — | Choose a [cloud service](#cloud-ai) or turn summaries off; story merging still works |

   The models were compared on real news (see `tools/benchmark_models.py`).
4. If Ollama runs on another computer, enter its address under **Settings → Artificial intelligence → Ollama address**.

### How much the AI writes

Thousands of reports arrive every day, and on most computers the AI cannot summarise each of them on its own
(~8 seconds per report). Under **Settings → Artificial intelligence → How much the AI writes**:

| Option | What it does | For |
|---|---|---|
| **Every report** | Every report is summarised on its own. | A strong graphics card or a fast cloud service |
| **Stories together** | Reports of an event covered by several sources are not read separately: the story summary covers them, and the link to your country is taken from it. Single reports are summarised one by one. | Medium |
| **Fast** (default) | Single reports are also read ten at a time: headline, category and the link to your country. The summary is written when you click **Summarise** on the report. | Slower computers |

The rules for the link to your country are the same in all three: the AI only extracts the countries and topics in
the text, and fixed rules decide.

### Summary languages

Under **Settings → Artificial intelligence → Summary languages** you choose 1–4 languages from more than 30. The
default is the interface language plus English. Headlines and summaries are written in all of them. The language
button on the cards switches between them, and outputs can be made in any of them. If you add a language later, older
articles are filled in the background. Every language adds work: in Ollama four languages take about three times as
long as one.

### Changing the instructions

Under **Settings → AI instructions** you can rewrite the instruction texts that go to the model (local or cloud) with
every request to suit your own guidelines: the report summary, the story summary, the full-text translation and the
search words. The default text of each is shown in the editor, and "Reset instruction to default" brings it back. The
program fills in placeholders such as `{languages}` and `{fields}`. The answer's format, the check that numbers exist in
the source and the length limits are fixed; a change only affects work done afterwards, summaries already written stay.

### Cloud AI

If you have no graphics card, or yours is not strong enough, a cloud service can write the headlines and summaries.
Choose it under **Settings → Artificial intelligence → Where the AI runs**:

| Service | Where to get a key | Note |
|---|---|---|
| **Google Gemini** | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | Has a free quota. |
| **OpenAI-compatible** | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | Other services with the same interface also work (OpenRouter, Groq, Mistral, DeepSeek…): enter their address under **Service address**. LM Studio on your own computer works this way too, without a key. |
| **Anthropic Claude** | [console.anthropic.com](https://console.anthropic.com/settings/keys) | |

1. Choose the service, paste the **API key** from your own account and press **Save**.
2. **Test connection** lists the service's models. Pick one in the **Model** box.
3. Free plans accept few requests per minute, so set **Requests per minute (max.)** to match your plan. If the limit is
   exceeded, the app waits and continues by itself.

> **Note:** With a cloud service, the text of the articles is sent to that service, **including full texts you read
> with your subscriptions**. The service's terms, its cost and the copyright of these texts are your responsibility.
> If you do not want that, use Ollama.

The key is stored only on this computer, encrypted with Windows encryption tied to your user account (DPAPI). It is
never shown again and never goes into logs or backups. Even with a cloud service, story merging is done on your
computer by `bge-m3` in Ollama.

### Problems

If Ollama is closed or a model is missing, the app does not crash. A warning at the top of the screen gives the
reason, and articles are shown in their original languages. To keep summaries reliable, the numbers in each summary are
checked against the source. If a number does not appear in the source, a "Check" warning is shown.

## Using it

- **Feed.** The *Stories* view shows reports of the same event on one card, in order of importance. The labels under
  each card say why ("5 sources", "4 sources in 3 hours", "Related to Brazil"). The *Articles* view lists single
  reports, newest first. At the top are search, a time range and filters: region, source group, language, category,
  source and "Related to (your country)". **Outside my region** in the region filter means every source outside Türkiye. **Your filters are remembered.** The source-group filter has two more
  choices: **Exclusives** (reports the publisher marks "Exclusive") and **Articles** (opinion, analysis, columns),
  both gathered from every source.
- **My country.** The "Related to (your country)" filter and labels follow the country chosen under Settings → **My
  country**. The default is Windows' region setting. A report is rated after the AI has read it:
  - it is *directly* related if your country appears in it;
  - it is *indirectly* related if it mentions a neighbour, one of the related countries you chose, or one of your topics.

  You can add topics from the suggestions, remove them, or write your own. If you do not want this, switch off
  **Use my country**: the link then does not count in the score, its filter and labels are hidden, and the AI no
  longer asks the country and topic questions (it works faster). **Country labels** can be switched off on their own:
  changing the country then does not rate older reports again.
- **Full text.** Clicking a report (its headline) opens it inside the program; a text not there yet is asked for, with
  the summary shown meanwhile. **Go to source** opens the site. The **Fetch full text** button on a card also queues it,
  and **Read full text** opens it
  (for your own reading only; never in outputs). If you switch on Settings → Full text → **Translate the full text
  too**, every full text that arrives is also translated into your summary languages; the default is the summary only.
- **Working hours.** Settings → Background. The default is to work day and night (you can leave the program open all
  the time); you can pick a time window, and outside it collecting news, the AI and full texts rest. What you ask for
  by hand (Summarise, fetch the full text, Scan now) is still done.
- **Story detail.** Summary, a breakdown of the score, day-by-day development, all reports with links, and your notes.
  **First to report** on the card names the outlet that published first; where outlets contradict each other on a fact,
  the AI writes the difference as an **Outlets disagree** note (in newly written summaries only).
  Use **Remove from this story** for a wrongly grouped report and **Merge with another story** for two stories about
  the same event.
- **Meeting.** Today's list of proposals. Use **Add to meeting** (or `T`) on a story, reorder by dragging, and write a
  short reason for each proposal.
- **Notebook.** Pick a day in the calendar to see that day's free note, meeting list and story notes.
- **Outputs.** Every output window offers:
  - **Copy formatted**: pastes cleanly into Word and Outlook;
  - **Copy plain text**: for apps such as WhatsApp;
  - **Send by e-mail**: opens a formatted draft if desktop Outlook is installed. Otherwise it opens a plain-text draft
    in the computer's default mail app; long text is shortened there, and the full text is also copied to the
    clipboard. The app never **sends** the e-mail itself; you add the recipient and send it;
  - **Print / PDF**: for a PDF, choose "Microsoft Print to PDF" as the printer.

  You also choose the output language from your summary languages. The **morning briefing** lists the most important
  stories of the chosen time range by category.
- **Statistics.** Choose a period at the top (24 hours, 7 days, 30 days); everything is counted for it. Type a topic
  under *Topic trend* (it is also searched in your sources' languages) to see in how many reports it appears per hour
  or day and its share of all reports. *News by category* counts only reports whose category the AI has decided, and
  says how many that is. *Region of the reporting press* is the source's region, not where the event happened.
  *Rising* lists the stories that grew fastest in the last hours; click one to open it. The *Sources* table also shows
  sources that sent nothing. Changes are against the previous period of equal length, and are not shown while
  collection does not reach that far back. Every chart can also be shown as a table.
- **History.** Pick a day in the calendar. *Morning 09:00* shows that morning's ranking and *Whole day* the ranking at
  the end of the day. Search covers all days and ignores case and Turkish-specific letters.
- **Search also runs in other languages.** The words you type are searched at once. If the AI is on, they are
  translated within a few seconds into the languages your sources publish in ("kuzey kore iha" → "North Korea drone",
  "Северная Корея беспилотник" …), and those reports are added to the list. The line under the search box shows the
  translations used. Most foreign reports have no summary in your language, so without this a search only finds
  reports in the language you typed or ones the AI has summarised.
- **Sources.** Turn sources on and off, and give them a reliability weight and a media group; sources of the same group
  count as one. Use **Add source** to test and add your own RSS address. If you do not know the RSS address, type the
  site's address: the app suggests the site's RSS links and the news sitemaps it is allowed to read. Broken feeds are
  shown in red with the reason.
- **Settings.** Theme (system / light / dark), interface language, AI, story and score settings, your interest
  profile (keywords, categories, regions), my country, full text, retention, notifications and quiet hours, backups
  and updates.

**Keyboard shortcuts:** `J` / `K` next / previous, `Enter` or `O` open, `T` add to meeting, `/` search.

## Subscription sites: the browser extension

Reports from subscription sites (especially **exclusives** that appear only there) can be read by World Signal through
**a small extension in your own browser**: the pages are opened not by a separate automation browser of the program but
by your own Chromium-based browser (Chrome, Brave, Edge, Opera), with your profile and your session. The program decides which report is read when; the
extension only opens the page in a background tab (in a minimized window if the browser has no window open), looks
at it for a few seconds, scrolls down like a reader, hands the page to the program and closes the tab. No window comes
to the front.

**One-time setup, three steps** (Settings → Full text → **Extension** shows the same steps):

1. Open your browser's extensions page (`chrome://extensions`, `brave://extensions`, `edge://extensions`, `opera://extensions`), turn on
   **Developer mode**, choose **Load unpacked** and pick the `extension` folder inside the program folder (the **Open
   the extension folder** button in Settings opens it).
2. Click the extension's icon and paste the **pairing code** from Settings (**Copy code**).
3. Be signed in to your subscription sites in that browser.

Then set the reader to **Extension** under Settings → Full text; the rest runs by itself (if Settings asks you to
restart the program once, do so). What you need to know:

- **Tried, but only a little:** the extension worked in Brave on most subscription sites (more than 40 reports in the
  first hour); some sites (e.g. Le Monde, FT) sometimes did not give the page. Watch the result the first time you use it.
- **The browser must be open.** If it is closed the program can start it without a window (switch this off in
  Settings); while the extension is paused or the browser cannot start, no page is read, the jobs wait in the queue and
  the sidebar shows a one-line warning.
- **Robot checks (CAPTCHAs) and similar protections are never solved.** If such a page appears, the report is marked
  "blocked" and the site is rested for longer and longer intervals. On a page the extension only scrolls; it does not
  click, type or submit forms.
- **Sites' terms of use may forbid automated reading even for subscribers.** You take that risk (including a warning to
  or the closing of your account). The pace limits (interval per site, daily limit, night rest) are under Settings →
  Full text; the defaults are low.
- The extension opens only addresses the program gives it, and talks to the program only inside this computer, with a
  randomly generated pairing code; before sending the code it first verifies that the program holding the same code
  listens on the very port it asked (another program holding that port and relaying the question to the real program
  cannot pass this check).
  **New code** replaces the code (the old extension connection stops working).
- The extension is not published in a browser store; when the program is updated the extension folder is updated too,
  and you press **Reload** once on the browser's extensions page.
- The earlier way remains (not recommended): if the reader is set to **The program's browser**, pages are opened with a
  separate browser profile that belongs to the program. The [clear rules](#copyright-and-subscriptions) above apply here too.

## Copyright and subscriptions

World Signal republishes nobody's content; it shows it only on **your** screen.

> **To be clear: World Signal does not get around paywalls and does not get around bot protection.**
>
> - It takes an article's full text only when **you** have a valid subscription and session on that site, from the
>   page your own browser already shows. Without a subscription only the public headline, summary and link appear.
> - If a robot check, CAPTCHA, Cloudflare or a similar protection appears, it **stops**: it does not try to solve or
>   evade it, it skips the page and rests that site for a while.
> - There are no archive or paywall-bypass sites, no fake identity or fake fingerprint, no IP hiding (proxy/VPN), and
>   no use of anybody else's account or session.
> - Full texts are for your local use only: they go into no output, to no server (other than a cloud AI service you
>   choose yourself) and are not shared.
>
> This is not legal advice. Many sites' terms of use may **forbid automated reading, even for subscribers**; keeping to
> the terms and any consequences (including a warning or closing of your account) are **yours**. If a site's terms do
> not allow automated reading, switch full text off for that site (Sources → the source's "Full text" setting).

- Articles come from publishers' public RSS feeds: headline, short summary and link. For a few sources without RSS,
  Bing News' public RSS search is used, and the links lead straight to the publisher. The Reuters and AP websites are
  closed to automated readers, so these agencies are followed section by section through Bing search.
- Some sites without RSS are read from the **news sitemap** they publish for search engines. This is done only if the
  site's robots.txt allows automated readers.
- **Paid sites:** you can read a whole article only if **you** subscribe to that site. Open the site from
  **Sources → Subscription sites** and sign in once with your own account. With the reader set to **Extension** (see
  [the browser extension](#subscription-sites-the-browser-extension)) the session stays in your own browser; with
  **The program's browser** it is kept only on this computer, in a separate browser profile that belongs to World
  Signal. Without a subscription you see only the headline, the short summary and the link.
- The app does not get around paywalls, does not solve robot checks (CAPTCHAs), and does not use archive or
  paywall-bypass sites. It opens pages at a human pace: one page at a time, a few pages per site per hour.
  Subscription sites (read in the browser) go slower still: at least 20 minutes between two pages of one site
  (3 minutes for pages you ask for), at most 15 pages per site per day, no pages opened by themselves between 00:00
  and 07:00, and each page is read and scrolled for 20-60 seconds after it opens. These can be changed under
  Settings → Full text.
- **Full texts never go into any output.** Copies, prints, PDFs and e-mails contain only the summaries, source names
  and links.
- If you choose a [cloud AI](#cloud-ai) service, you are responsible for the texts sent to it for summarising,
  including full texts.
- Feeds you add yourself, such as the private RSS address of an agency your organisation subscribes to, stay only in
  your database. They are sent nowhere and are not part of this repository.

## Privacy and security

The app talks only to:

- the sources' RSS feeds and, when you ask for a full text, the article pages;
- the Ollama address (by default your own computer: `localhost`);
- **only if you choose one**, a cloud AI service (Google Gemini, an OpenAI-compatible service or Anthropic Claude),
  which receives the article texts to summarise (full texts included) and the search words to translate;
- GitHub, only for new-version information and downloads (can be turned off).

The browser extension (if you use it) talks to the app only inside this computer (`127.0.0.1`).

No usage data, statistics or personal information is collected or sent. The app's interface is a local server that is
reachable only from this computer (`127.0.0.1`) and only with a secret key that changes at every start. The database,
notes, browser profile and session cookies stay only under `%LOCALAPPDATA%\WorldSignal`. Cloud API keys are kept in
the same folder (`secrets.json`), encrypted with Windows encryption tied to your user account (DPAPI). They do not go
into backups.

## Troubleshooting

| Problem | What to do |
|---|---|
| The app does not start | A message window gives the reason and the location of the log file: `%LOCALAPPDATA%\WorldSignal\logs\worldsignal.log`. |
| "Failed to resolve Python.Runtime.Loader.Initialize" | A version older than 0.11.2 was extracted from a zip downloaded from the internet. Download the newest version, or right-click the zip → **Properties → Unblock**, and extract it again. |
| Nothing happens on a second double-click | The app is already running in the tray, and the existing window comes to the front. To quit completely, right-click the tray icon → **Exit**. |
| Headlines and summaries are not in my language | They are written by the AI (Ollama or a cloud service). Without either, articles appear in their original languages (see [AI](#artificial-intelligence-optional)). Also check that your language is selected under **Summary languages**. |
| "Summaries unavailable: Ollama cannot be reached" | Ollama is closed or not installed. Start it, choose a cloud service, or turn summaries off under Settings → Artificial intelligence. |
| "The API key was not accepted" / "rate limit reached" | If the key is invalid or expired, enter a new one under Settings → Artificial intelligence. At a rate limit the app waits and continues. If it happens often, lower **Requests per minute (max.)**. |
| Summaries are very slow and the graphics card gets hot | Choose a smaller model (see the [table](#setting-up-ollama)). |
| A source is shown in red | The Sources page gives the reason: site down, address changed, closed to automated readers… |
| Full text says "paywall" | Sign in to that site (in your own browser if you use the extension, otherwise under Sources → Subscription sites). Without a subscription, no full text can be fetched. |
| "Extension not connected" | The browser may be closed, the extension not loaded or paused; the extension's icon shows its state. Paste the pairing code again from Settings → Full text → Extension. If the app was restarted and Settings says so, restart the app once. |
| "The update failed" | A file in the program folder was in use, and the next attempt will try again. If it keeps failing, download the new zip and extract it. |
| Something went wrong | Under Settings → **Backups**, restore the backup of an earlier day; the app restarts. |

## Development

Stack: Python 3.12 (FastAPI, SQLite + FTS5, feedparser, trafilatura, patchright) · React 19 + TypeScript + Vite ·
pywebview/WebView2 · PyInstaller. The project documents are in Turkish:
- architecture: [ARCHITECTURE.md](ARCHITECTURE.md);
- version history: [CHANGELOG.en.md](CHANGELOG.en.md) (English from 0.10.0) and [CHANGELOG.md](CHANGELOG.md);
- source verification report: [docs/KAYNAK_DOGRULAMA.md](docs/KAYNAK_DOGRULAMA.md).

Country data (`src/worldsignal/catalog/countries.json`): country names from [Wikidata](https://www.wikidata.org) (CC0),
land borders from [GeoNames](https://www.geonames.org) (CC BY 4.0).

```
uv sync --python 3.12                        # Python environment
cd frontend && npm ci && npm run build       # build the interface
.venv\Scripts\python -m worldsignal          # run with a window
.venv\Scripts\python -m pytest               # backend and end-to-end tests
cd frontend && npm test                      # interface tests
.venv\Scripts\python tools\verify_catalog.py # re-verify the source catalogue
```

The source catalogue is edited in `tools/catalog_candidates.json`. `tools/verify_catalog.py` tries every feed and
writes `src/worldsignal/catalog/sources.json`; do not edit that file by hand.

**Publishing a release** (project owner):

1. Raise the version number (`pyproject.toml`, `src/worldsignal/__init__.py`, `frontend/package.json`) and write that
   version's section in both `CHANGELOG.md` (Turkish) and `CHANGELOG.en.md` (English). Together they become the
   release notes on GitHub; "What's new" in the app shows the part in its interface language. Without both, no package
   is made.
2. Run `scripts\clean-build-release.bat`. It cleans up, runs all tests, backs up the source, builds the app, and
   prepares and checks the zip, `.sha256` and notes under `release\<version>\`. It stops if a part is missing or user
   data slipped in.
3. Run `scripts\publish.bat`. It scans the source for personal data, pushes it to the repository and creates the GitHub
   release tagged `v<version>`. Every installed World Signal sees the release at its next check. To try it first:
   `scripts\publish.bat --dry-run`.
