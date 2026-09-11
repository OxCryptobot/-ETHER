# -*- mode: python ; coding: utf-8 -*-
a = Analysis(
    ["ether_app.py"],
    pathex=["."],
    binaries=[],
    datas=[("ether_ui.html", ".")],
    hiddenimports=["live_host", "webview"],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="ETHER", debug=False, strip=False, upx=True, console=False)
