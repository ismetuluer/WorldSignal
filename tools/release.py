"""Turn the last build into a release: the zip that goes to GitHub, its checksum and the release notes.

    .venv\\Scripts\\python tools\\release.py              (run by scripts\\clean-build-release.bat)
    .venv\\Scripts\\python tools\\release.py --verify <zip>

release\\<version>\\
    WorldSignal-<version>-windows.zip          the program folder (top folder "WorldSignal")
    WorldSignal-<version>-windows.zip.sha256   checked by the updater before it unpacks anything
    NOTES.md                                    this version's CHANGELOG sections, Turkish and English (the GitHub
                                                release text; the app shows the part in its interface language)
The two newest release folders are kept. tools\\publish.py puts one on GitHub.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "dist" / "WorldSignal"
RELEASES = ROOT / "release"
KEEP = 2
TOP = "WorldSignal"
# Never shipped: a database, logs, backups, the browser profile, the instance file.
FORBIDDEN = re.compile(r"(\.db|\.db-wal|\.db-shm|\.log|instance\.json|instance\.lock)$|/(browser-profile|backups|logs)/",
                       re.IGNORECASE)
REQUIRED = {
    "program (WorldSignal.exe)": f"{TOP}/WorldSignal.exe",
    "sürüm bilgisi": f"{TOP}/version.txt",
    "indirilen zip'te açılış ayarı (WorldSignal.exe.config)": f"{TOP}/WorldSignal.exe.config",
    "tarayıcı eklentisi (extension/manifest.json)": f"{TOP}/extension/manifest.json",
    "arayüz dosyaları": f"{TOP}/_internal/worldsignal/ui/index.html",
    "kaynak kataloğu": f"{TOP}/_internal/worldsignal/catalog/sources.json",
    "ülke verisi": f"{TOP}/_internal/worldsignal/catalog/countries.json",
}


def fail(msg: str) -> None:
    print(f"  HATA: {msg}")
    sys.exit(1)


def zip_name(version: str) -> str:
    return f"WorldSignal-{version}-windows.zip"


# Headings that separate the two languages in the release notes; frontend/src/components/Update.tsx splits on them.
NOTES_TR, NOTES_EN = "## Türkçe", "## English"


def changelog_section(version: str, changelog: Path) -> str:
    """The section of ``version`` in one changelog, without its heading."""
    text = changelog.read_text(encoding="utf-8") if changelog.is_file() else ""
    m = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", text, re.MULTILINE | re.DOTALL)
    if not m or not m.group(1).strip():
        fail(f"{changelog.name} içinde {version} bölümü yok; önce değişiklikleri yazın")
    return m.group(1).strip()


def release_notes(version: str, changelog: Path = ROOT / "CHANGELOG.md",
                  changelog_en: Path = ROOT / "CHANGELOG.en.md") -> str:
    """The release notes of ``version``: its Turkish and its English changelog section."""
    tr = changelog_section(version, changelog)
    en = changelog_section(version, changelog_en)
    return f"{NOTES_TR}\n\n{tr}\n\n{NOTES_EN}\n\n{en}\n"


def verify(package: Path, version: str) -> None:
    """The zip is complete, carries the right version and no user data."""
    with zipfile.ZipFile(package) as zf:
        names = set(zf.namelist())
        checks = {label: path in names for label, path in REQUIRED.items()}
        checks["veritabanı göçleri"] = any(n.startswith(f"{TOP}/_internal/worldsignal/db/migrations/0") for n in names)
        checks["tek üst klasör"] = all(PurePosixPath(n).parts[0] == TOP for n in names)
        stamp = zf.read(f"{TOP}/version.txt").decode("utf-8").strip() if checks["sürüm bilgisi"] else None
        checks[f"sürüm {version}"] = stamp == version
        for label, ok in checks.items():
            print(f"  {'tamam' if ok else 'EKSİK'}  {label}")
        if not all(checks.values()):
            fail("paket eksik ya da hatalı")
        leaked = sorted(n for n in names if FORBIDDEN.search("/" + n))
        if leaked:
            fail(f"pakette kullanıcı verisi var: {leaked[:3]}")
    digest = (package.parent / f"{package.name}.sha256").read_text(encoding="utf-8").split()[0]
    if hashlib.sha256(package.read_bytes()).hexdigest() != digest:
        fail("sağlama değeri (sha256) tutmuyor")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", type=Path, help="only check an existing release zip")
    args = parser.parse_args()
    if args.verify:
        version = re.fullmatch(r"WorldSignal-(.+)-windows\.zip", args.verify.name)
        verify(args.verify, version.group(1) if version else "?")
        return

    if not (APP / "version.txt").is_file():
        fail("derleme bulunamadı; önce tools\\build.py çalışmalı")
    version = (APP / "version.txt").read_text(encoding="utf-8").strip()
    notes = release_notes(version)
    folder = RELEASES / version
    tmp = RELEASES / f"{version}.partial"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    package = tmp / zip_name(version)
    print(f"  Sıkıştırılıyor: {package.name} ...", flush=True)
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(APP.rglob("*")):
            if path.is_file():
                zf.write(path, f"{TOP}/{path.relative_to(APP).as_posix()}")
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    (tmp / f"{package.name}.sha256").write_text(f"{digest}  {package.name}\n", encoding="utf-8")
    (tmp / "NOTES.md").write_text(notes, encoding="utf-8")
    verify(package, version)
    shutil.rmtree(folder, ignore_errors=True)  # a rebuild of the same version replaces the old package
    tmp.rename(folder)
    old = sorted((p for p in RELEASES.iterdir() if p.is_dir() and not p.name.endswith(".partial")),
                 key=lambda p: p.stat().st_mtime, reverse=True)[KEEP:]
    for p in old:
        shutil.rmtree(p, ignore_errors=True)
        print(f"  eski paket silindi: {p.name}")
    final = folder / package.name
    print(f"  Paket: {final} ({final.stat().st_size / 1_000_000:.0f} MB)")


if __name__ == "__main__":
    main()
