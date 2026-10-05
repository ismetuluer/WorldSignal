"""Publish the newest release on GitHub (run by scripts\\publish.bat).

    .venv\\Scripts\\python tools\\publish.py [--dry-run]
    .venv\\Scripts\\python tools\\publish.py --docs "message" [--dry-run]

1. Checks the release zip in release\\<version>\\ (tools\\release.py) and that the version is not on GitHub yet.
2. Exports the source code to the public repository's working copy: only files tracked by git, minus
   PRIVATE (project notes, documents with publishers' text). Every exported file is scanned for the
   personal and company data listed in publish.private.json (kept on this computer only, never
   exported); one hit stops the publication. The public repository therefore gets one commit per
   release and never this computer's history.
3. Commits, tags v<version>, pushes, and creates the GitHub release with the zip, its .sha256 and the
   release notes. Every World Signal checks for it (worldsignal/updater.py).

--docs: only the README files and docs\\ (screenshots, plans) go to the public repository, as one ordinary
commit without a version, tag or release; the source code and the release stay as they are. The same scan runs.

publish.private.json (in the project folder, ignored by git):
    {"repo": "owner/WorldSignal", "public_dir": "C:\\\\...\\\\WorldSignal-public",
     "author": "Name <id+user@users.noreply.github.com>", "forbidden": ["internal-host", "user.name", ...]}
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASES = ROOT / "release"
CONFIG = ROOT / "publish.private.json"
# Never published: private project notes and documents that quote publishers' feed texts.
PRIVATE = ("CLAUDE.md", "HANDOFF.md", ".claude/", "docs/MODEL_KARSILASTIRMA.md",
           "docs/superpowers/specs/2026-10-02-android-uygulamasi-design.md",
           "docs/superpowers/plans/2026-10-02-android-")  # the personal-device Android plans name the owner
# Also stops a publication, whatever the private list says: absolute user paths and personal e-mail.
GENERIC = [r"[A-Za-z]:\\{1,2}Users\\{1,2}(?!Public\\)[^\\\s]+",r"@gmail\.com", r"@hotmail\.com", r"@outlook\.com"]

sys.path.insert(0, str(ROOT / "tools"))
from release import verify, zip_name  # noqa: E402


def say(msg: str) -> None:
    print(msg, flush=True)


def fail(msg: str) -> None:
    say(f"  HATA: {msg}")
    sys.exit(1)


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True, encoding="utf-8")


def load_config(path: Path = CONFIG) -> dict:
    if not path.is_file():
        fail(f"{path.name} yok. İçeriği için tools\\publish.py'nin başındaki açıklamaya bakın.")
    config = json.loads(path.read_text(encoding="utf-8"))
    for key in ("repo", "public_dir", "author", "forbidden"):
        if not config.get(key):
            fail(f"{path.name} içinde '{key}' eksik")
    return config


def public_files(root: Path = ROOT) -> list[str]:
    tracked = run(["git", "ls-files", "-z"], cwd=root).stdout.split("\0")
    return sorted(f for f in tracked if f and not f.startswith(PRIVATE) and (root / f).is_file())


def scan(files: list[str], forbidden: list[str], root: Path = ROOT) -> list[str]:
    """Lines that contain personal or company data (file:line: pattern)."""
    # A plain word matches only as a whole word ("Paul" must not hit "Pauline").
    patterns = [re.compile(rf"(?<![A-Za-z0-9]){re.escape(w)}(?![A-Za-z0-9])" if w.isalnum() else re.escape(w),
                           re.IGNORECASE) for w in forbidden]
    patterns += [re.compile(p) for p in GENERIC]
    hits = []
    for f in files:
        try:
            text = (root / f).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary files (icons) carry no text
        for n, line in enumerate(text.splitlines(), 1):
            for p in patterns:
                if p.search(line):
                    hits.append(f"{f}:{n}: {p.pattern}")
    return hits


def export(files: list[str], target: Path, root: Path = ROOT) -> None:
    for item in target.iterdir():
        if item.name == ".git":
            continue
        shutil.rmtree(item) if item.is_dir() else item.unlink()
    for f in files:
        dst = target / f
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / f, dst)


def is_doc(path: str) -> bool:
    return bool(re.fullmatch(r"README(\.[a-z]{2})?\.md", path)) or path.startswith("docs/")


def publish_docs(config: dict, message: str, dry_run: bool) -> None:
    """README files and docs/ only: scanned, copied over the public working copy, one commit, pushed."""
    repo, target = config["repo"], Path(config["public_dir"])
    say("[1/3] Belgeler kişisel veri için taranıyor...")
    files = [f for f in public_files() if is_doc(f)]
    hits = scan(files, config["forbidden"])
    if hits:
        for h in hits[:30]:
            say(f"  BULUNDU  {h}")
        fail(f"{len(hits)} satırda kişisel/şirket verisi var; bunlar temizlenmeden yayın yapılmaz.")
    say(f"  Temiz: {len(files)} dosya (görseller metin taşımadığı için elle gözden geçirilir).")
    say(f"[2/3] Herkese açık kopya hazırlanıyor: {target}")
    if not (target / ".git").is_dir():
        run(["gh", "repo", "clone", repo, str(target)])
    run(["git", "pull", "--ff-only"], cwd=target, check=False)
    for f in files:
        dst = target / f
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f, dst)
    run(["git", "add", "-A"], cwd=target)
    changes = run(["git", "status", "--short"], cwd=target).stdout.splitlines()
    if dry_run or not changes:
        say(f"  {len(changes)} dosya değişecek; hiçbir şey kaydedilmedi ve gönderilmedi." if changes else "  Değişiklik yok.")
        return
    name, email = re.fullmatch(r"(.+?)\s*<(.+)>", config["author"]).groups()  # type: ignore[union-attr]
    ident = ["-c", f"user.name={name}", "-c", f"user.email={email}"]
    run(["git", *ident, "commit", "-m", message], cwd=target)
    say("[3/3] GitHub'a gönderiliyor...")
    push = run(["git", "push", "origin", "HEAD:main"], cwd=target, check=False)
    if push.returncode != 0:
        fail(f"gönderilemedi:\n{push.stderr}")
    say(f"\n  YAYINLANDI: {len(changes)} dosya, https://github.com/{repo}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="check and export, but do not push or release")
    parser.add_argument("--docs", metavar="MESSAGE", help="publish only README files and docs/ as one commit")
    args = parser.parse_args()
    config = load_config()
    repo, target = config["repo"], Path(config["public_dir"])
    if args.docs:
        publish_docs(config, args.docs, args.dry_run)
        return
    sys.path.insert(0, str(ROOT / "src"))
    from worldsignal import __version__ as version

    say(f"[1/5] Paket kontrol ediliyor: World Signal {version}")
    folder = RELEASES / version
    package = folder / zip_name(version)
    if not package.is_file():
        fail(f"{package} yok. Önce scripts\\clean-build-release.bat çalıştırın.")
    verify(package, version)
    if run(["gh", "auth", "status"], check=False).returncode != 0:
        fail("GitHub'a giriş yapılmamış: bir kez 'gh auth login' çalıştırın.")
    if run(["gh", "release", "view", f"v{version}", "--repo", repo], check=False).returncode == 0:
        fail(f"v{version} GitHub'da zaten yayında. Yeni yayın için sürüm numarasını artırın.")

    say("[2/5] Kaynak kod kişisel veri için taranıyor...")
    files = public_files()
    hits = scan(files, config["forbidden"])
    if hits:
        for h in hits[:30]:
            say(f"  BULUNDU  {h}")
        fail(f"{len(hits)} satırda kişisel/şirket verisi var; bunlar temizlenmeden yayın yapılmaz.")
    say(f"  Temiz: {len(files)} dosya.")

    say(f"[3/5] Herkese açık kopya hazırlanıyor: {target}")
    if not (target / ".git").is_dir():
        run(["gh", "repo", "clone", repo, str(target)])
    run(["git", "pull", "--ff-only"], cwd=target, check=False)  # an empty new repository has nothing to pull
    export(files, target)
    run(["git", "add", "-A"], cwd=target)
    if args.dry_run:
        changes = run(["git", "status", "--short"], cwd=target).stdout.splitlines()
        say(f"  Deneme: {len(changes)} dosya değişecekti; hiçbir şey kaydedilmedi ve gönderilmedi.")
        say(f"  Gönderilecek dosyalar {target} klasöründe incelenebilir.")
        return
    name, email = re.fullmatch(r"(.+?)\s*<(.+)>", config["author"]).groups()  # type: ignore[union-attr]
    ident = ["-c", f"user.name={name}", "-c", f"user.email={email}"]
    run(["git", *ident, "commit", "--allow-empty", "-m", f"World Signal {version}"], cwd=target)
    run(["git", *ident, "tag", "-a", f"v{version}", "-m", f"World Signal {version}"], cwd=target)

    say("[4/5] GitHub'a gönderiliyor...")
    push = run(["git", "push", "-u", "origin", "HEAD:main", "--follow-tags"], cwd=target, check=False)
    if push.returncode != 0:
        fail(f"gönderilemedi:\n{push.stderr}")

    say("[5/5] GitHub sürümü oluşturuluyor...")
    created = run(["gh", "release", "create", f"v{version}", str(package), str(folder / f"{package.name}.sha256"),
                   "--repo", repo, "--title", f"World Signal {version}", "--notes-file", str(folder / "NOTES.md"),
                   "--verify-tag"], check=False)
    if created.returncode != 0:
        fail(f"sürüm oluşturulamadı:\n{created.stderr}")
    say(f"\n  YAYINLANDI: {created.stdout.strip()}\n  Programlar bu sürümü bir sonraki denetimde (en geç 6 saat) görür.")


if __name__ == "__main__":
    main()
