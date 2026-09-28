# PyInstaller build of World Signal: one folder, no installation (tools/build.py runs this).
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821 - defined by PyInstaller
SRC = ROOT / "src" / "worldsignal"

datas = [
    (str(ROOT / "frontend" / "dist"), "worldsignal/ui"),
    (str(SRC / "catalog" / "sources.json"), "worldsignal/catalog"),
    (str(SRC / "db" / "migrations"), "worldsignal/db/migrations"),
    (str(SRC / "assets" / "worldsignal.ico"), "worldsignal/assets"),
]
# Text extraction needs its language data; patchright needs its browser driver (node + scripts).
for package in ("trafilatura", "justext", "courlan", "htmldate", "patchright"):
    datas += collect_data_files(package)

hiddenimports = collect_submodules("worldsignal") + collect_submodules("uvicorn") + collect_submodules("patchright")

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "launch.py")],
    pathex=[str(ROOT / "src")],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "playwright", "IPython", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WorldSignal",
    icon=str(SRC / "assets" / "worldsignal.ico"),
    console=False,
    upx=False,
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="WorldSignal", upx=False)  # noqa: F821
