"""Build the program.

    .venv\\Scripts\\python tools\\build.py [--skip-ui]

Output: dist\\WorldSignal\\ (one folder, WorldSignal.exe inside) with version.txt (read by the updater)
and build.txt (version + build time, e.g. 0.8.0_20260928_101500, written to the log at start-up).
scripts\\clean-build-release.bat turns this into the release zip (tools\\release.py).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
APP = DIST / "WorldSignal"


def run(cmd: list[str], cwd: Path) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True, shell=(cmd[0] == "npm"))  # npm is a .cmd on Windows


def main() -> str:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-ui", action="store_true", help="the web interface is already built")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "src"))
    from worldsignal import __version__

    build_id = f"{__version__}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    t0 = time.monotonic()
    if not args.skip_ui:
        run(["npm", "run", "build"], ROOT / "frontend")
    shutil.rmtree(APP, ignore_errors=True)
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(DIST),
         "--workpath", str(ROOT / "build"), str(ROOT / "packaging" / "worldsignal.spec")], ROOT)
    (APP / "version.txt").write_text(__version__, encoding="utf-8")
    (APP / "build.txt").write_text(build_id, encoding="utf-8")
    shutil.copy2(ROOT / "packaging" / "WorldSignal.exe.config", APP / "WorldSignal.exe.config")
    files = [p for p in APP.rglob("*") if p.is_file()]
    size = sum(p.stat().st_size for p in files) / 1_000_000
    print(f"Built {build_id}: {APP} - {len(files)} files, {size:.0f} MB; {time.monotonic() - t0:.0f} s")
    return build_id


if __name__ == "__main__":
    main()
