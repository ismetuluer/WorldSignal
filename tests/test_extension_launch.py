"""The extension finds the program on a fixed port; the program starts the user's browser when it is closed."""

import socket
import subprocess
from datetime import timedelta
from pathlib import Path

from test_extension_bridge import Clock
from test_fulltext import world  # noqa: F401
from worldsignal.__main__ import ServerThread, server_ports
from worldsignal.fulltext.bridge import ExtensionBridge
from worldsignal.fulltext.fetch import BrowserInfo
from worldsignal.fulltext.launcher import is_running


def test_the_fixed_ports_are_tried_first():
    assert server_ports(0) == [*range(47821, 47831), 0]
    assert server_ports(8765) == [8765]  # development: --port wins


def test_a_taken_port_is_skipped():
    taken = socket.socket()
    taken.bind(("127.0.0.1", 0))
    port = taken.getsockname()[1]
    try:
        server = ServerThread(lambda scope, receive, send: None, [port, 0])
        assert server.port not in (0, port)
        server.sock.close()
    finally:
        taken.close()


def test_is_running_reads_the_task_list():
    class Done:
        def __init__(self, out):
            self.stdout = out

    assert is_running(Path("C:/x/brave.exe"), run=lambda *a, **k: Done('"brave.exe","123","Console"'))
    assert not is_running(Path("C:/x/brave.exe"), run=lambda *a, **k: Done("INFO: No tasks are running"))


def test_a_hung_task_list_counts_as_running():
    """tasklist times out: assume the browser runs, so no second copy is ever started on a doubt."""
    def hung(*args, **kwargs):
        assert kwargs["timeout"] == 10
        raise subprocess.TimeoutExpired("tasklist", 10)

    assert is_running(Path("C:/x/brave.exe"), run=hung)


def test_the_browser_is_started_only_when_needed(world):  # noqa: F811
    world["settings"].set("fulltext.enabled", True)
    clock = Clock()
    bridge = ExtensionBridge(world["repo"], world["settings"], resting=lambda: False, clock=clock)
    brave = BrowserInfo("Brave", Path("brave.exe"), Path("profile"))
    started = []
    launch = lambda: bridge.launch_if_needed(lambda p: brave, lambda exe, profile: False, lambda exe, profile: started.append(exe))  # noqa: E731
    assert launch() and started == [brave.executable]  # never heard from the extension: start it
    assert not launch()  # not again within half an hour
    clock.now += timedelta(minutes=31)
    bridge.last_seen = clock.now - timedelta(minutes=2)
    assert not launch()  # the extension talks: nothing to do
    world["settings"].set("fulltext.launch_browser", False)
    bridge.last_seen = None
    clock.now += timedelta(hours=1)
    assert not launch()


def test_with_the_own_profile_that_profile_has_to_be_open_not_the_browser(world, tmp_path):  # noqa: F811
    world["settings"].set("extension.profile", "own")
    bridge = ExtensionBridge(world["repo"], world["settings"], resting=lambda: False, clock=Clock(), own_profile=tmp_path / "own")
    brave = BrowserInfo("Brave", Path("brave.exe"), Path("profile"))
    asked, started = [], []

    def running(exe, profile):
        asked.append(profile)
        return True  # the everyday browser would be running; the own profile is not asked as "the browser"

    assert not bridge.launch_if_needed(lambda p: brave, running, lambda exe, profile: started.append((exe, profile)))
    assert asked == [tmp_path / "own"] and started == []
    bridge._launched_at = None
    assert bridge.launch_if_needed(lambda p: brave, lambda exe, profile: False, lambda exe, profile: started.append((exe, profile)))
    assert started == [(brave.executable, tmp_path / "own")]


def test_the_own_profile_is_started_on_its_own_folder_without_a_window(tmp_path):
    from worldsignal.fulltext.launcher import start_hidden

    calls = []
    start_hidden(Path("brave.exe"), tmp_path / "own", popen=lambda args, **k: calls.append(args))
    start_hidden(Path("brave.exe"), popen=lambda args, **k: calls.append(args))
    assert calls[0][0] == "brave.exe" and f"--user-data-dir={(tmp_path / 'own').resolve()}" in calls[0] and calls[0][-1] == "--no-startup-window"
    assert calls[1] == ["brave.exe", "--no-startup-window"]  # no profile: the everyday browser, as before
    assert (tmp_path / "own").is_dir()


def test_is_running_with_a_profile_asks_the_profile_lock(tmp_path):
    assert not is_running(Path("brave.exe"), tmp_path)  # nobody holds the profile
