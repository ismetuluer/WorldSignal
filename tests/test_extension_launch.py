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


def test_ports_in_extension_mode():
    assert server_ports(0, "automation") == [0]
    assert server_ports(0, "extension") == [*range(47821, 47831), 0]
    assert server_ports(8765, "extension") == [8765]  # development: --port wins


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
    world["settings"].set("fulltext.reader", "extension")
    clock = Clock()
    bridge = ExtensionBridge(world["repo"], world["settings"], resting=lambda: False, clock=clock)
    brave = BrowserInfo("Brave", Path("brave.exe"), Path("profile"))
    started = []
    launch = lambda: bridge.launch_if_needed(lambda p: brave, lambda exe: False, started.append)  # noqa: E731
    assert launch() and started == [brave.executable]  # never heard from the extension: start it
    assert not launch()  # not again within half an hour
    clock.now += timedelta(minutes=31)
    bridge.last_seen = clock.now - timedelta(minutes=2)
    assert not launch()  # the extension talks: nothing to do
    world["settings"].set("fulltext.launch_browser", False)
    bridge.last_seen = None
    clock.now += timedelta(hours=1)
    assert not launch()
