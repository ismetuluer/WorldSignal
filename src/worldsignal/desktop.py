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
        window.restore()
        window.show()
        window.on_top = True
        window.on_top = False

    def quit_app() -> None:
        state["quitting"] = True
        window.destroy()

    def restart() -> None:
        state["restart"] = True
        quit_app()

    def open_story(story_id: int | None) -> None:
        show()
        if story_id:
            window.evaluate_js(f"window.location.hash = '#/feed?story={int(story_id)}'")

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
