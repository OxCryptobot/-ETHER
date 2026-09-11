# -*- mode: python ; coding: utf-8 -*-
a = Analysis(
    ["scripts/ether_app.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=["scripts.live_host", "scripts.ether_app"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "webview"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ETHER",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
