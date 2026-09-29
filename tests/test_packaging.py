"""The release zip (tools/release.py) and the public export (tools/publish.py), on real folders."""

import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import publish  # noqa: E402
import release  # noqa: E402

TOP = "WorldSignal"
GOOD = {
    f"{TOP}/WorldSignal.exe": "exe",
    f"{TOP}/version.txt": "0.8.0",
    f"{TOP}/WorldSignal.exe.config": "<configuration/>",
    f"{TOP}/_internal/worldsignal/ui/index.html": "<html>",
    f"{TOP}/_internal/worldsignal/catalog/sources.json": "{}",
    f"{TOP}/_internal/worldsignal/catalog/countries.json": "{}",
    f"{TOP}/_internal/worldsignal/db/migrations/0001_initial.sql": "--",
    f"{TOP}/_internal/patchright/driver/node.exe": "x",
}


def make_zip(folder: Path, files: dict[str, str], version: str = "0.8.0") -> Path:
    package = folder / release.zip_name(version)
    with zipfile.ZipFile(package, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    (folder / f"{package.name}.sha256").write_text(f"{digest}  {package.name}\n", encoding="utf-8")
    return package


def test_a_complete_package_passes(tmp_path):
    release.verify(make_zip(tmp_path, GOOD), "0.8.0")


@pytest.mark.parametrize("change", [
    {"drop": f"{TOP}/_internal/patchright/driver/node.exe"},
    {"drop": f"{TOP}/version.txt"},
    {"drop": f"{TOP}/WorldSignal.exe.config"},
    {"add": ("stray.txt", "outside the top folder")},
    {"add": (f"{TOP}/worldsignal.db", "a database")},
    {"add": (f"{TOP}/logs/worldsignal.log", "a log")},
    {"add": (f"{TOP}/browser-profile/Default/Cookies", "cookies")},
])
def test_a_broken_or_leaking_package_is_refused(tmp_path, change):
    files = dict(GOOD)
    files.pop(change.get("drop", ""), None)
    if "add" in change:
        files[change["add"][0]] = change["add"][1]
    with pytest.raises(SystemExit):
        release.verify(make_zip(tmp_path, files), "0.8.0")


def test_wrong_version_or_checksum_is_refused(tmp_path):
    with pytest.raises(SystemExit):
        release.verify(make_zip(tmp_path, GOOD), "0.9.0")
    package = make_zip(tmp_path, GOOD)
    (tmp_path / f"{package.name}.sha256").write_text("0" * 64, encoding="utf-8")
    with pytest.raises(SystemExit):
        release.verify(package, "0.8.0")


def test_release_notes_come_from_both_changelogs(tmp_path):
    log = tmp_path / "CHANGELOG.md"
    log.write_text("# Log\n\n## [0.9.0] — 2026 — B\n\n- yeni\n\n## [0.8.0] — 2026 — A\n\n- eski\n", encoding="utf-8")
    log_en = tmp_path / "CHANGELOG.en.md"
    log_en.write_text("# Log\n\n## [0.9.0] — 2026 — B\n\n- new\n", encoding="utf-8")
    assert release.release_notes("0.9.0", log, log_en) == "## Türkçe\n\n- yeni\n\n## English\n\n- new\n"
    with pytest.raises(SystemExit):
        release.release_notes("0.8.0", log, log_en)  # no English section: no release
    with pytest.raises(SystemExit):
        release.release_notes("1.0.0", log, log_en)


def test_the_real_changelog_has_this_versions_notes():
    sys.path.insert(0, str(ROOT / "src"))
    from worldsignal import __version__

    assert release.release_notes(__version__).strip()


# -- public export -------------------------------------------------------------------------------------------
@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (root / "README.md").write_text("World Signal\n", encoding="utf-8")
    (root / "CLAUDE.md").write_text("private notes of the owner\n", encoding="utf-8")
    (root / "docs" / "MODEL_KARSILASTIRMA.md").write_text("publisher text\n", encoding="utf-8")
    (root / "untracked.txt").write_text("not in git\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "src", "README.md", "CLAUDE.md", "docs"], cwd=root, check=True)
    return root


def test_only_tracked_public_files_are_exported(repo, tmp_path):
    files = publish.public_files(repo)
    assert files == ["README.md", "src/app.py"]
    target = tmp_path / "public"
    (target / ".git").mkdir(parents=True)
    (target / "old_file.txt").write_text("from the previous release", encoding="utf-8")
    publish.export(files, target, repo)
    assert sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()) == ["README.md", "src/app.py"]
    assert (target / ".git").is_dir()  # the public history is kept


def test_personal_data_stops_the_publication(repo):
    (repo / "src" / "app.py").write_text(
        'SHARE = r"\\\\intranet-host\\Haber"\nPATH = "C:\\\\Users\\\\jane.doe\\\\AppData"\nowner = "Pauline Media"\n',
        encoding="utf-8")
    hits = publish.scan(["src/app.py", "README.md"], ["intranet-host", "Paul"], repo)
    lines = sorted({h.split(": ", 1)[0] for h in hits})
    # Line 1: the private list; line 2: a real user folder, even without a private list;
    # line 3 is clean: "Pauline" is not the name "Paul".
    assert lines == ["src/app.py:1", "src/app.py:2"]
    (repo / "README.md").write_text("Made by Paul.\n", encoding="utf-8")
    assert publish.scan(["README.md"], ["Paul"], repo) == ["README.md:1: (?<![A-Za-z0-9])Paul(?![A-Za-z0-9])"]


def test_the_real_project_is_clean_by_its_generic_rules():
    """Whatever the private list holds, no user folder or personal e-mail may be in a public file."""
    assert publish.scan(publish.public_files(), []) == []
