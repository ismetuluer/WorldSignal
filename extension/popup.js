import { call, findProgram } from "./lib.js";

const t = (name, subs) => chrome.i18n.getMessage(name, subs);
for (const el of document.querySelectorAll("[data-msg]")) el.textContent = t(el.dataset.msg);

const { key, paused, lastError } = await chrome.storage.local.get({ key: "", paused: false, lastError: "" });
document.getElementById("paused").checked = paused;
document.getElementById("error").textContent = lastError ? t("lastError", [lastError]) : "";

async function show() {
  const state = document.getElementById("state");
  const { key: k, paused: isPaused } = await chrome.storage.local.get({ key: "", paused: false });
  if (isPaused) return void (state.textContent = t("pausedState"));
  if (!k) return void (state.textContent = t("notPaired"));
  // The key is sent only to a program that proves it holds the same code.
  const port = await findProgram(fetch, k);
  if (port == null) return void (state.textContent = t("notFoundOrWrongCode"));
  try {
    const s = await call(fetch, port, k, "/api/ext/status");
    state.textContent = s.reading ? t("reading", [s.reading]) : t("connected", [String(s.read_today)]);
  } catch (e) {
    // 401: wrong code. http_NNN: the program answered but failed, so say what happened. Anything else: not reachable.
    if (e.message === "not_paired") state.textContent = t("wrongCode");
    else if (/^http_/.test(e.message)) state.textContent = t("lastError", [e.message]);
    else state.textContent = t("noProgram");
  }
}

document.getElementById("save").addEventListener("click", async () => {
  await chrome.storage.local.set({ key: document.getElementById("code").value.trim() });
  chrome.runtime.sendMessage("round");
  await show();
});
document.getElementById("paused").addEventListener("change", async (e) => {
  await chrome.storage.local.set({ paused: e.target.checked });
  await show();
});
if (key) document.getElementById("code").placeholder = "••••••";
await show();
