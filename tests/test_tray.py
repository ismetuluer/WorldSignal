"""System tray on the real Windows shell: icon added, clicks and menu commands reach their handlers."""

import ctypes
import os
import threading
import time

import pytest

from worldsignal.paths import resource_dir

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows system tray")

from worldsignal.tray import CMD_OPEN, CMD_QUIT, CMD_SCAN, NIN_BALLOONUSERCLICK, WM_COMMAND, WM_LBUTTONUP, WM_TRAY, Tray  # noqa: E402

ICON = resource_dir() / "assets" / "worldsignal.ico"


def wait_for(cond, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def tray():
    calls: list[tuple] = []
    t = Tray(
        "World Signal test", ICON,
        on_open=lambda: calls.append(("open",)),
        on_scan=lambda: calls.append(("scan",)),
        on_quit=lambda: calls.append(("quit",)),
        on_notification_click=lambda sid: calls.append(("click", sid)),
        menu_texts=lambda: {"open": "Aç", "scan": "Tara", "quit": "Çık"},
        status_line=lambda: "Durum",
    )
    t.calls = calls
    assert t.start(), "icon was not added to the notification area"
    yield t
    t.stop()


def post(t, msg, wparam, lparam):
    ctypes.windll.user32.PostMessageW(ctypes.c_void_p(t.hwnd), msg, wparam, lparam)


def test_icon_clicks_and_commands(tray):
    assert tray.hwnd and ICON.is_file()
    post(tray, WM_TRAY, 0, WM_LBUTTONUP)
    for cmd in (CMD_OPEN, CMD_SCAN, CMD_QUIT):
        post(tray, WM_COMMAND, cmd, 0)
    tray.last_story_id = 42
    post(tray, WM_TRAY, 0, NIN_BALLOONUSERCLICK)
    assert wait_for(lambda: len(tray.calls) == 5)
    assert tray.calls == [("open",), ("open",), ("scan",), ("quit",), ("click", 42)]


def test_a_failing_handler_does_not_kill_the_tray(tray):
    tray.on_scan = lambda: 1 / 0
    post(tray, WM_COMMAND, CMD_SCAN, 0)
    post(tray, WM_COMMAND, CMD_OPEN, 0)
    assert wait_for(lambda: ("open",) in tray.calls)


def test_stop_removes_the_icon_and_ends_the_thread(tray):
    thread = tray._thread
    tray.stop()
    assert not thread.is_alive() and tray.hwnd is None
    assert tray.notify("x", "y") is False  # nothing to show on


def test_tooltip_can_change(tray):
    tray.set_tooltip("World Signal · 12 yeni haber" + "x" * 300)
    assert len(tray.tooltip) == 127


@pytest.mark.desktop
def test_notification_is_shown(tray):
    assert tray.notify("World Signal test", "Bu bir deneme bildirimidir.", 7)
    time.sleep(3)
    assert tray.last_story_id == 7


def test_start_twice_in_one_process_is_fine():
    done = threading.Event()
    trays = []
    for _ in range(2):
        t = Tray("t", None, on_open=done.set, on_scan=done.set, on_quit=done.set,
                 on_notification_click=lambda s: None, menu_texts=dict, status_line=str)
        assert t.start()
        trays.append(t)
    for t in trays:
        t.stop()
