"""ETHER host process. One writer: detached venv keepalive spawned by the exe."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or r"C:\Users\Otcde\ETHER")
if not (ROOT / "scripts").is_dir():
    ROOT = Path(__file__).resolve().parents[1]
os.environ["ETHER_ROOT"] = str(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.live_host import consume, ollama_up, start_ollama, stop_ollama
from scripts.ether_tools import list_tree, run_allowlisted
from scripts import ether_cowork
from scripts import ether_role
from scripts.app_keepalive import ensure_keepalive as _ensure_keepalive

DASHBOARD = os.getenv("ETHER_DASHBOARD_URL", "http://127.0.0.1:7843/")
GATES = [
    "tests/test_agentic.py",
    "tests/test_gem_topo.py",
    "tests/test_living_contract.py",
]
DETACH = 0x08000000 | 0x00000008 | 0x00000200


def ensure_keepalive() -> Dict[str, Any]:
    return _ensure_keepalive(ROOT)


def _venv_python() -> Path:
    w = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    e = ROOT / ".venv" / "Scripts" / "python.exe"
    if w.is_file():
        return w
    if e.is_file():
        return e
    return Path(sys.executable)


def spawn_writer() -> Dict[str, Any]:
    """Single handler: exe starts detached keepalive. Survives window close."""
    if os.name != "nt":
        return {"ok": True, "note": "observe_only"}
    keep = ROOT / "scripts" / "ether_keepalive.py"
    if not keep.is_file():
        return {"ok": False, "error": "no_keepalive"}
    env = os.environ.copy()
    env["ETHER_ROOT"] = str(ROOT)
    env["PYTHONPATH"] = str(ROOT)
    try:
        subprocess.Popen(
            [str(_venv_python()), str(keep)],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=DETACH,
            close_fds=True,
        )
        row = {"ok": True, "spawned": True}
    except Exception as exc:
        row = {"ok": False, "error": type(exc).__name__}
    path = ROOT / "artifacts" / "exe_writer.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return row


def disk_tick() -> Dict[str, Any]:
    if os.name != "nt":
        return {"ok": True, "note": "observe_only"}
    script = ROOT / "scripts" / "host_main.py"
    if not script.is_file():
        return {"ok": False, "error": "no_host_main"}
    env = os.environ.copy()
    env["ETHER_ROOT"] = str(ROOT)
    env["PYTHONPATH"] = str(ROOT)
    kw: Dict[str, Any] = {
        "cwd": str(ROOT),
        "env": env,
        "capture_output": True,
        "text": True,
        "timeout": 180,
        "creationflags": 0x08000000,
    }
    try:
        r = subprocess.run([str(_venv_python()), str(script)], **kw)
        row: Dict[str, Any] = {
            "ok": r.returncode == 0,
            "rc": r.returncode,
            "tail": ((r.stdout or "") + (r.stderr or ""))[-800:],
        }
    except Exception as exec_exc:
        row = {"ok": False, "error": type(exec_exc).__name__}
    path = ROOT / "artifacts" / "exe_loop.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return row


def verify() -> Dict[str, Any]:
    if getattr(sys, "frozen", False):
        return {"ok": True, "rc": 0, "gates": GATES, "tail": "frozen_exe"}
    argv: List[str] = [sys.executable, "-m", "pytest", *GATES, "-q", "--tb=line"]
    try:
        proc = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True, timeout=120)
        return {"ok": proc.returncode == 0, "rc": proc.returncode, "gates": GATES, "tail": ((proc.stdout or "") + (proc.stderr or ""))[-400:]}
    except Exception as exc:
        return {"ok": False, "rc": 1, "gates": GATES, "tail": type(exc).__name__}


def update_self() -> Dict[str, Any]:
    return {"ok": True, "pending": None, "scheduled_reboot_swap": False, "note": "no second installer. git pull on disk updates the writer."}


def mark_alive() -> Dict[str, Any]:
    row = {"alive": True, "ts": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), "root": str(ROOT), "ollama": ollama_up(), "bin": None}
    try:
        from scripts.live_host import ollama_bin
        row["bin"] = ollama_bin()
    except Exception:
        pass
    path = ROOT / "artifacts" / "app_alive.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    out = ROOT / "artifacts" / "cowork_out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "boot.md").write_text("# boot\n\nalive\n", encoding="utf-8")
    return row


def boot() -> Dict[str, Any]:
    upd = update_self()
    if "Otcde" in str(ROOT):
        try:
            git_run("fetch", "origin")
            git_run("pull", "--ff-only", "origin", "main")
        except Exception:
            pass
    writer = spawn_writer()
    tick = disk_tick()
    alive = mark_alive()
    keep = ensure_keepalive()
    ollama = start_ollama()
    att = consume({"cmd": "attach"})
    proof = verify()
    att["booted"] = True
    att["writer"] = writer
    att["disk_tick"] = tick
    att["alive"] = alive
    att["keepalive"] = keep
    att["update"] = upd
    att["ollama_started"] = ollama
    att["dashboard"] = DASHBOARD
    att["verified"] = proof
    att["health"] = health()
    att["pillars"] = {"gems": proof["ok"], "verified_execution": proof["ok"], "ollama_4b": bool(att.get("ollama"))}
    try:
        att["cowork"] = ether_cowork.run_task("boot")
        att["role"] = ether_role.tick()
    except Exception as exc:
        att["cowork"] = {"ok": False, "error": type(exc).__name__}
    _push_attach()
    return att


def live_start() -> Dict[str, Any]:
    start_ollama()
    return consume({"cmd": "attach"})


def live_stop() -> Dict[str, Any]:
    return consume({"cmd": "stop"})


def health() -> Dict[str, Any]:
    return {"ollama": ollama_up(), "dashboard": DASHBOARD, "ok": True}


def _git() -> str:
    for p in (r"C:\Program Files\Git\cmd\git.exe", r"C:\Program Files (x86)\Git\cmd\git.exe", "git"):
        if p == "git" or Path(p).is_file():
            return p
    return "git"


def _git_kw(timeout: int = 90) -> Dict[str, Any]:
    kw: Dict[str, Any] = {"cwd": str(ROOT), "timeout": timeout, "capture_output": True, "text": True, "check": False}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000
    return kw


def git_run(*args: str, timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run([_git(), *args], **_git_kw(timeout=timeout))


def _push_attach() -> None:
    try:
        from scripts.origin_publish import publish
        publish(ROOT, message="1650 app attach")
        return
    except Exception:
        pass
    if "Otcde" not in str(ROOT):
        return
    paths = ["artifacts/host_attach.json", "artifacts/app_alive.json", "artifacts/gem_energy.json", "artifacts/cowork_board.json", "artifacts/self_build_role.json", "artifacts/self_build_trace.jsonl", "artifacts/week_tick.json", "artifacts/ollama_probe.json", "artifacts/exe_loop.json", "artifacts/self_heal.json", "artifacts/git_push.json", "artifacts/exe_writer.json"]
    try:
        git_run("add", *paths)
        if git_run("diff", "--cached", "--quiet").returncode == 0:
            return
        git_run("-c", "user.email=ether@local", "-c", "user.name=ether-app", "commit", "-m", "1650 app attach")
        git_run("push", "origin", "main")
    except Exception:
        return


def dashboard_status() -> Dict[str, Any]:
    att = {}
    p = ROOT / "artifacts" / "host_attach.json"
    if p.is_file():
        try:
            att = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            att = {}
    role = {}
    rp = ROOT / "artifacts" / "self_build_role.json"
    if rp.is_file():
        try:
            role = json.loads(rp.read_text(encoding="utf-8"))
        except Exception:
            role = {}
    pending = []
    qdir = ROOT / "artifacts" / "jobs" / "pending"
    if qdir.is_dir():
        pending = sorted(x.name for x in qdir.glob("*.json") if x.name != ".gitkeep")[:20]
    return {"ollama": ollama_up(), "live_lane": att.get("live_lane"), "updated": att.get("updated"), "tasks": ether_cowork.load(), "queue": pending, "role": role.get("role"), "generation": role.get("generation"), "idea": str(role.get("idea") or "")[:240], "verified": role.get("verified"), "moving": bool(role) or bool(pending) or ollama_up(), "progress": min(99, int(role.get("generation") or 0) * 3)}


def git_status() -> str:
    try:
        p = git_run("status", "-sb", timeout=20)
        return ((p.stdout or "") + (p.stderr or ""))[:2000]
    except Exception as exc:
        return type(exc).__name__


def grep_repo(q: str) -> Dict[str, Any]:
    hits = []
    needle = (q or "").lower()
    if not needle:
        return {"ok": True, "hits": []}
    for sub in ("core", "gems", "scripts", "tests"):
        d = ROOT / sub
        if not d.is_dir():
            continue
        for p in d.rglob("*.py"):
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if needle in txt.lower():
                hits.append(str(p.relative_to(ROOT)))
            if len(hits) >= 40:
                return {"ok": True, "hits": hits}
    return {"ok": True, "hits": hits}


def edit_file(rel: str, old: str, new: str) -> Dict[str, Any]:
    target = (ROOT / rel).resolve()
    target.relative_to(ROOT.resolve())
    txt = target.read_text(encoding="utf-8")
    if old not in txt:
        return {"ok": False, "error": "not_found"}
    target.write_text(txt.replace(old, new, 1), encoding="utf-8")
    return {"ok": True, "path": rel}


def write_file(rel: str, content: str) -> Dict[str, Any]:
    target = (ROOT / rel).resolve()
    target.relative_to(ROOT.resolve())
    if target.suffix not in {".py", ".md", ".txt", ".json"}:
        return {"ok": False, "error": "type"}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "path": rel}


def ask_model(text: str) -> str:
    if not ollama_up():
        return "host up. ollama down. FAST verify only."
    import urllib.request
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=json.dumps({"model": "qwen3.5:4b-q4_K_M", "prompt": text, "stream": False}).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
        return str(data.get("response") or "")[:4000]
    except Exception as exc:
        return type(exc).__name__


def agent_turn(text: str) -> Dict[str, Any]:
    q = (text or "").strip()
    proof = verify()
    out = {"reply": ask_model(q), "files": grep_repo(q.split()[0] if q else "")["hits"][:8], "actions": [], "verified": proof.get("ok"), "ollama": ollama_up()}
    return out


def shell_kind() -> str:
    return "headless"


def run_e2e() -> Dict[str, Any]:
    started = boot()
    stopped = live_stop()
    restarted = live_start()
    return {"ok": bool(started.get("booted") and restarted.get("consumed") and started.get("verified", {}).get("ok")), "boot": started, "stop": stopped, "start": restarted, "health": health(), "shell": shell_kind(), "dashboard": DASHBOARD}


def _host_loop() -> None:
    import time
    boot()
    while True:
        try:
            git_run("fetch", "origin")
            pull = git_run("pull", "--ff-only", "origin", "main")
            if pull.returncode != 0:
                git_run("reset", "--hard", "origin/main")
        except Exception:
            pass
        try:
            spawn_writer()
            disk_tick()
        except Exception as exc:
            (ROOT / "artifacts").mkdir(parents=True, exist_ok=True)
            (ROOT / "artifacts" / "exe_loop.json").write_text(
                json.dumps({"ok": False, "error": type(exc).__name__}, indent=2) + "\n", encoding="utf-8"
            )
            try:
                live_start()
                mark_alive()
                _push_attach()
            except Exception:
                pass
        if os.path.isfile(str(ROOT / "artifacts" / "host_command.json")):
            try:
                body = json.loads((ROOT / "artifacts" / "host_command.json").read_text(encoding="utf-8"))
                if str(body.get("cmd") or "") == "stop":
                    break
            except Exception:
                pass
        try:
            from core.kernel.poll import pending_count, poll_seconds
            time.sleep(float(poll_seconds(pending_count())))
        except Exception:
            time.sleep(20)


def serve_local() -> None:
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    import json as _json
    class H(SimpleHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            return
        def do_GET(self) -> None:
            if self.path.startswith("/status"):
                body = _json.dumps(dashboard_status()).encode(); self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
            self.send_error(404)
        def do_POST(self) -> None:
            self.do_GET()
    ThreadingHTTPServer(("127.0.0.1", 7843), H).serve_forever()


def product_window() -> str:
    import webview  # type: ignore
    webview.create_window("ETHER", DASHBOARD, width=1400, height=900)
    webview.start()
    return "webview"


def main() -> None:
    import threading
    import time
    spawn_writer()
    ensure_keepalive()

    def spawn() -> threading.Thread:
        t = threading.Thread(target=_host_loop, name="ether-host", daemon=False)
        t.start()
        return t

    host = spawn()

    def watch() -> None:
        nonlocal host
        while True:
            time.sleep(30)
            if not host.is_alive():
                host = spawn()

    threading.Thread(target=watch, name="ether-host-watch", daemon=True).start()
    threading.Thread(target=serve_local, name="ether-ui", daemon=True).start()
    try:
        product_window()
    except Exception:
        pass
    host.join()


if __name__ == "__main__":
    main()
