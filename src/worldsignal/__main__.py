"""World Signal entry point.

    python -m worldsignal                 # desktop window (normal use)
    python -m worldsignal --server-only   # API + UI in the browser (development)
"""

from __future__ import annotations

import argparse
import logging
import os
import secrets
import socket
import sys
import threading
import time
from pathlib import Path

import uvicorn

from . import __version__
from .api.app import create_app
from .backup import apply_pending_restore
from .bootstrap import build_context
from .logging_setup import setup_logging
from .paths import DataPaths, default_data_dir, ui_dist_dir
from .single_instance import InstanceLock, activate_running_instance

log = logging.getLogger("worldsignal")

WINDOW_TITLE = "World Signal"
# Where the program was started; main() moves to the data folder (see there).
START_DIR = os.getcwd()


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="worldsignal", description="World Signal")
    p.add_argument("--server-only", action="store_true", help="API ve arayüzü pencere açmadan sun (geliştirme)")
    p.add_argument("--port", type=int, default=0, help="Sabit port (varsayılan: rastgele boş port)")
    p.add_argument("--token", default=None, help="Sabit erişim anahtarı (yalnızca geliştirme)")
    p.add_argument("--data-dir", type=Path, default=None, help="Veri klasörü (varsayılan: %%LOCALAPPDATA%%\\WorldSignal)")
    p.add_argument("--no-collector", action="store_true", help="Arka planda haber toplamayı başlatma")
    p.add_argument("--debug", action="store_true", help="Ayrıntılı günlük")
    p.add_argument("--after-pid", type=int, default=None, help=argparse.SUPPRESS)  # restart: wait for the old process
    p.add_argument("--apply-update", type=Path, default=None, help=argparse.SUPPRESS)  # updater.py: replace this folder
    return p.parse_args(argv)


def run_apply_update(args: argparse.Namespace, paths: DataPaths) -> int:
    """This is the downloaded new program: put it in place of the old one and start it there."""
    import subprocess

    from .updater import apply_update

    install_dir = args.apply_update.resolve()
    source_dir = Path(sys.executable).resolve().parent
    ok = apply_update(install_dir, source_dir, paths.root,
                      wait=lambda: wait_for_exit(args.after_pid, 60) if args.after_pid else None)
    if not ok:
        show_error_box("World Signal güncellenemedi; önceki sürüm açılıyor.\n\n"
                       f"Ayrıntılar günlük dosyasında: {paths.logs / 'worldsignal.log'}")
    exe = install_dir / "WorldSignal.exe"
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([str(exe), f"--data-dir={paths.root}", f"--after-pid={os.getpid()}"],  # noqa: S603
                     close_fds=True, creationflags=flags, cwd=paths.root)
    return 0 if ok else 1


def show_error_box(message: str) -> None:
    """Show a native error dialog (the user may not have a console)."""
    if os.name == "nt":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, WINDOW_TITLE, 0x10)
    else:
        print(message, file=sys.stderr)


class ServerThread:
    def __init__(self, app, port: int) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", port))
        self.port = self.sock.getsockname()[1]
        config = uvicorn.Config(app, log_config=None, access_log=False, lifespan="on")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self._run, name="server", daemon=True)

    def _run(self) -> None:
        self.server.run(sockets=[self.sock])

    def start(self, timeout: float = 30) -> None:
        self.thread.start()
        deadline = time.monotonic() + timeout
        while not self.server.started:
            if not self.thread.is_alive():
                raise RuntimeError("Server thread exited during start-up")
            if time.monotonic() > deadline:
                raise RuntimeError("Server did not start in time")
            time.sleep(0.05)

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = DataPaths((args.data_dir or default_data_dir()).resolve()).ensure()
    setup_logging(paths.logs, logging.DEBUG if args.debug else logging.INFO, console=args.server_only)
    log.info("World Signal %s starting (data: %s)", __version__, paths.root)
    # Leave the program folder (Explorer makes it the current directory): otherwise this process and its browser
    # child processes keep it in use and the next update cannot replace it. All paths are absolute.
    os.chdir(paths.root)

    if args.apply_update:
        return run_apply_update(args, paths)
    if args.after_pid:
        wait_for_exit(args.after_pid)  # a restart: the old process must have let go of the database
    lock = InstanceLock(paths.lock_file, paths.instance_file)
    if not lock.acquire():
        log.info("Another instance is running; activating it")
        if not activate_running_instance(paths.instance_file):
            show_error_box("World Signal zaten çalışıyor ancak penceresine ulaşılamadı.\n"
                           "Görev Yöneticisi'nden eski World Signal işlemini kapatıp yeniden deneyin.")
        return 0

    server = None
    restart = False
    try:
        restored = apply_pending_restore(paths.database, paths.backups, paths.root)
        if restored is not None:
            log.info("Pending restore handled: %s", restored)
        token = args.token or secrets.token_urlsafe(32)
        ctx = build_context(paths, token, ui_dist_dir(), run_collector=not args.no_collector)
        app = create_app(ctx)
        server = ServerThread(app, args.port)
        server.start()
        lock.publish(server.port, token)
        url = f"http://127.0.0.1:{server.port}/?t={token}"
        log.info("Serving on http://127.0.0.1:%d", server.port)

        if args.server_only:
            print(f"World Signal çalışıyor: {url}\nDurdurmak için Ctrl+C.", flush=True)
            try:
                while server.thread.is_alive():
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass
        else:
            from .desktop import run_window

            restart = run_window(ctx, url)
        return 0
    except Exception as exc:
        log.exception("Fatal start-up error")
        show_error_box(
            "World Signal başlatılamadı.\n\n"
            f"Hata: {exc}\n\n"
            f"Ayrıntılar günlük dosyasında: {paths.logs / 'worldsignal.log'}"
        )
        return 1
    finally:
        if server is not None:
            server.stop()
        lock.release()
        log.info("World Signal stopped")
        if restart:
            start_again()


def wait_for_exit(pid: int, timeout: float = 30.0) -> None:
    """Wait until process ``pid`` has ended (or the timeout passed)."""
    if os.name != "nt":
        return
    import ctypes

    synchronize = 0x00100000
    handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        return  # already gone
    try:
        ctypes.windll.kernel32.WaitForSingleObject(handle, int(timeout * 1000))
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def start_again() -> None:
    """Start a new World Signal process (after this one released the instance lock)."""
    import subprocess

    args = [a for a in sys.argv[1:] if not a.startswith("--after-pid")]
    args += [f"--after-pid={os.getpid()}"]
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, *args]
    else:
        cmd = [sys.executable, "-m", "worldsignal", *args]
    log.info("Restarting: %s", cmd)
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    # The arguments may hold paths relative to the directory this program was started in.
    subprocess.Popen(cmd, close_fds=True, creationflags=flags, cwd=START_DIR)  # noqa: S603 - our own executable


if __name__ == "__main__":
    sys.exit(main())
