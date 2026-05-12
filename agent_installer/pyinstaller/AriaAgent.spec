# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

block_cipher = None
root = Path(__file__).resolve().parents[2]

added = [
    (str(root / "modules"), "modules"),
    (str(root / "data_backend"), "data_backend"),
    (str(root / "config.py"), "."),
    (str(root / "main.py"), "."),
    (str(root / "run_data_backend.py"), "."),
]

a = Analysis(
    [str(root / "agent_installer" / "common" / "agent_entry.py")],
    pathex=[str(root)],
    binaries=[],
    datas=added,
    hiddenimports=["modules", "data_backend"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
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
    name="AriaAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
)
