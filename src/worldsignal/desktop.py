"""The desktop window, the tray icon and how they work together.

* Closing the window hides it and World Signal keeps collecting in the tray (``app.close_to_tray``);
  the first time this happens a notification says so. "Quit" in the tray menu really exits.
* The notifier shows its notifications through the tray; clicking one opens the story.
* ``ctx.restart`` closes everything and asks ``main`` to start the program again (after a restore).
* ``ctx.quit`` closes everything without starting again (an update starts the new program itself).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from .api.app import AppContext
from .paths import resource_dir

log = logging.getLogger(__name__)

WINDOW_TITLE = "World Signal"

TEXTS = {
    "tr": {
        "open": "World Signal'i aç",
        "scan": "Şimdi tara",
        "quit": "Çıkış",
        "scanning": "Kaynaklar taranıyor…",
        "last_scan": "Son tarama {time} · {new} yeni haber",
        "never": "Henüz tarama yapılmadı",
        "bg_title": "World Signal arka planda çalışıyor",
        "bg_body": "Haberler toplanmaya devam ediyor. Pencereyi açmak için tepsideki simgeye tıklayın; kapatmak için sağ tık → Çıkış.",
    },
    "en": {
        "open": "Open World Signal",
        "scan": "Scan now",
        "quit": "Quit",
        "scanning": "Scanning sources…",
        "last_scan": "Last scan {time} · {new} new articles",
        "never": "No scan yet",
        "bg_title": "World Signal keeps running",
        "bg_body": "News is still being collected. Click the tray icon to open the window; right-click → Quit to exit.",
    },
}


def native_show(title: str = WINDOW_TITLE) -> bool:
    """Bring the program's window to the front with plain Win32 calls. Returns False when there is no such window.

    Not through pywebview: its calls from another thread (the tray's, the server's) set properties of the window's form
    from that thread while it holds the interpreter lock, and when the window's own thread then needs the lock (a
    Python callback) both wait for each other and the whole program hangs (seen with ``window.on_top``). ctypes lets
    go of the lock during every call, so this cannot."""
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found: list[int] = []
    pid = os.getpid()

    def visit(hwnd: int, _lparam: int) -> bool:
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != pid:
            return True
        text = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, text, 256)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if text.value == title and not cls.value.startswith("WorldSignalTray"):
            found.append(hwnd)
        return True

    user32.EnumWindows(enum_proc(visit), 0)
    if not found:
        return False
    hwnd = found[0]
    sw_show, sw_restore = 5, 9
    user32.ShowWindow(hwnd, sw_restore if user32.IsIconic(hwnd) else sw_show)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    return True


def icon_path() -> Any:
    return resource_dir() / "assets" / "worldsignal.ico"


def texts_for(ctx: AppContext) -> dict[str, str]:
    return TEXTS.get(str(ctx.settings.get("ui.language")), TEXTS["tr"])


def status_line(ctx: AppContext) -> str:
    t = texts_for(ctx)
    st = ctx.collector.status()
    if st.get("busy"):
        return t["scanning"]
    last = st.get("last_cycle_at")
    if not last:
        return t["never"]
    local = datetime.fromisoformat(str(last).replace("Z", "+00:00")).astimezone()
    return t["last_scan"].format(time=local.strftime("%H:%M"), new=st.get("last_cycle_new", 0))


def windows_prefers_dark() -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        ) as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def run_window(ctx: AppContext, url: str) -> bool:
    """Show the window until the user quits. Returns True when a restart was requested."""
    import webview

    theme = ctx.settings.get("ui.theme")
    dark = theme == "dark" or (theme == "system" and windows_prefers_dark())
    window = webview.create_window(
        WINDOW_TITLE,
        url,
        width=1320,
        height=860,
        min_size=(880, 600),
        background_color="#1c1c1e" if dark else "#f5f5f7",
        text_select=True,
    )
    state = {"quitting": False, "restart": False, "told_background": False}

    def show() -> None:
        if not native_show():
            log.warning("The window to show was not found")

    def quit_app() -> None:
        state["quitting"] = True
        window.destroy()

    def restart() -> None:
        state["restart"] = True
        quit_app()

    def open_story(story_id: int | None) -> None:
        if story_id:
            ctx.extra["open_story"] = int(story_id)  # the page takes it with its next status poll (see /api/status)
        show()

    tray = None
    if os.name == "nt":
        from .tray import Tray

        tray = Tray(
            WINDOW_TITLE, icon_path(),
            on_open=show,
            on_scan=lambda: ctx.collector.request_run(),
            on_quit=quit_app,
            on_notification_click=open_story,
            menu_texts=lambda: texts_for(ctx),
            status_line=lambda: status_line(ctx),
        )
        if tray.start():
            ctx.notifier.show = tray.notify
        else:
            log.warning("No tray icon; closing the window will exit the program")
            tray = None

    def on_closing() -> bool:
        if state["quitting"] or tray is None or not ctx.settings.get("app.close_to_tray"):
            state["quitting"] = True
            return True
        window.hide()
        if not state["told_background"]:
            state["told_background"] = True
            t = texts_for(ctx)
            tray.notify(t["bg_title"], t["bg_body"], None)
        return False  # keep running in the tray

    window.events.closing += on_closing
    ctx.show_window = show
    ctx.restart = restart
    ctx.quit = quit_app
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    try:
        webview.start(gui="edgechromium", private_mode=False, storage_path=str(ctx.paths.root / "webview"))
    finally:
        ctx.notifier.show = None
        ctx.show_window = None
        ctx.restart = None
        ctx.quit = None
        if tray is not None:
            tray.stop()
    return state["restart"]
