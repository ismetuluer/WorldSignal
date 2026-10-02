import { call, findProgram, readPage, readingPlan, tick } from "./lib.js";

const state = { port: null, busy: false };

// Every round the program proves again that it holds the pairing code (the port found last time is asked first), so
// the key never goes to whatever took over a port after the program stopped.
async function port(key) {
  state.port = await findProgram(fetch, key, crypto, state.port);
  return state.port;
}

async function settings() {
  return chrome.storage.local.get({ key: "", paused: false });
}

// A service worker can be stopped by the browser in the middle of a read, so `finally` blocks cannot be relied on:
// the window being read is remembered and a later round closes what a stopped worker left behind.
async function closeStaleWindow() {
  const { readingWindow } = await chrome.storage.session.get({ readingWindow: null });
  if (readingWindow == null) return;
  await chrome.windows.remove(readingWindow).catch(() => undefined);
  await chrome.storage.session.remove("readingWindow");
}

// While a page is being read nothing else keeps the worker alive (Chrome stops an idle one after about 30 s), so an
// extension API call every 20 s counts as activity.
async function read(url) {
  const keepAlive = setInterval(() => void chrome.runtime.getPlatformInfo(), 20000);
  try {
    return await readPage(chrome, url, readingPlan(), {
      onWindow: (id) => chrome.storage.session.set({ readingWindow: id }),
      onClosed: () => chrome.storage.session.remove("readingWindow"),
    });
  } finally {
    clearInterval(keepAlive);
  }
}

async function round() {
  if (state.busy) return;
  state.busy = true;
  let wait = 60;
  try {
    await closeStaleWindow();
    wait = await tick({
      port,
      key: async () => (await settings()).key,
      paused: async () => (await settings()).paused,
      call: (p, k, path, body) => call(fetch, p, k, path, body),
      read,
    });
    await chrome.storage.local.set({ lastError: "" });
  } catch (e) {
    state.port = null; // the program may have restarted on another port
    await chrome.storage.local.set({ lastError: String(e.message || e) });
  } finally {
    state.busy = false;
  }
  // Chrome fires alarms no more often than every 30 s.
  const seconds = Math.max(wait, 30);
  await chrome.storage.local.set({ nextRoundAt: Date.now() + seconds * 1000 });
  chrome.alarms.create("round", { delayInMinutes: seconds / 60 });
}

// The one-shot "round" alarm is only re-created at the end of a round; if the worker was stopped mid-round the loop
// would stay dead. This periodic alarm restarts it, but only once the planned time (which honours the program's
// "wait_seconds") has passed, so it never hurries a resting site.
async function watchdog() {
  const { nextRoundAt } = await chrome.storage.local.get({ nextRoundAt: 0 });
  if (Date.now() >= nextRoundAt) await round();
}

chrome.alarms.create("watchdog", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "round") void round();
  else if (alarm.name === "watchdog") void watchdog();
});
chrome.runtime.onStartup.addListener(() => void round());
chrome.runtime.onInstalled.addListener(() => void round());
chrome.runtime.onMessage.addListener((msg) => {
  if (msg === "round") void round();
});
