# -*- mode: python ; coding: utf-8 -*-

block_cipher = None
import os

backend_dir = os.path.abspath(SPECPATH)
project_root = os.path.abspath(os.path.join(backend_dir, ".."))

a = Analysis(
    ["server.py"],
    pathex=[project_root, backend_dir],
    binaries=[],
    datas=[
        ("ai_models", "ai_models"),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.lifespan.on",
        "pydantic",
        "pydantic_core",
        "fastapi",
        "starlette",
        "pandas",
        "numpy",
        "openpyxl",
        "rapidfuzz",
        "sklearn",
        "joblib",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "qtpy",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
