# -*- mode: python ; coding: utf-8 -*-
import os
root = os.path.abspath("..")
datas = []
if os.path.isfile("ether_ui.html"):
    datas.append(("ether_ui.html", "."))
if os.path.isdir("matrix-ui"):
    datas.append(("matrix-ui", "matrix-ui"))
a = Analysis(
    ["ether_app.py"],
    pathex=[root, "."],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "live_host",
        "webview",
        "scripts.host_main",
        "scripts.origin_publish",
        "scripts.ether_keepalive",
        "scripts.self_heal",
        "scripts.unison",
        "scripts.app_keepalive",
        "scripts.runner_register",
        "scripts.live_status",
        "scripts.ether_evolve",
        "scripts.skills",
    ],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="ETHER", debug=False, strip=False, upx=False, console=False)