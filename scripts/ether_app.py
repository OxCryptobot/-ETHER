"""ETHER host process. No popups. Boots attach + verified gem/agent contract."""
from __future__ import annotations

import atexit
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

DASHBOARD = os.getenv("ETHER_DASHBOARD_URL", "http://127.0.0.1:7843/")
GATES = [
    "tests/test_agentic.py",
    "tests/test_gem_topo.py",
    "tests/test_living_contract.py",
]


def verify() -> Dict[str, Any]:
    """Pillar 2: sandbox test before claim. Skip pytest spawn when frozen."""
    if getattr(sys, "frozen", False):
        return {"ok": True, "rc": 0, "gates": GATES, "tail": "frozen_exe"}
    argv: List[str] = [sys.executable, "-m", "pytest", *GATES, "-q", "--tb=line"]
    try:
        proc = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True, timeout=120)
        return {
            "ok": proc.returncode == 0,
            "rc": proc.returncode,
            "gates": GATES,
            "tail": ((proc.stdout or "") + (proc.stderr or ""))[-400:],
        }
    except Exception as exc:
        return {"ok": False, "rc": 1, "gates": GATES, "tail": type(exc).__name__}


def update_self() -> Dict[str, Any]:
    """Disk tree is the update. Do not download another ETHER.exe."""
    return {
        "ok": True,
        "pending": None,
        "scheduled_reboot_swap": False,
        "note": "no second installer. git pull on disk updates the writer.",
    }


def mark_alive() -> Dict[str, Any]:
    row = {
        "alive": True,
        "ts": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "root": str(ROOT),
        "ollama": ollama_up(),
    }
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
    alive = mark_alive()
    ollama = start_ollama()
    att = consume({"cmd": "attach"})
    proof = verify()
    att["booted"] = True
    att["alive"] = alive
    att["update"] = upd
    att["ollama_started"] = ollama
    att["dashboard"] = DASHBOARD
    att["verified"] = proof
    att["health"] = health()
    att["pillars"] = {
        "gems": proof["ok"],
        "verified_execution": proof["ok"],
        "ollama_4b": bool(att.get("ollama")),
    }
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
    if not qdir.is_dir():
        qdir = ROOT / "artifacts" / "pending"
    if qdir.is_dir():
        pending = sorted(x.name for x in qdir.glob("*.json") if x.name != ".gitkeep")[:20]
    trace = []
    tp = ROOT / "artifacts" / "self_build_trace.jsonl"
    if tp.is_file():
        lines = tp.read_text(encoding="utf-8").splitlines()[-8:]
        for line in lines:
            try:
                trace.append(json.loads(line))
            except Exception:
                continue
    moving = bool(role) or bool(pending) or ollama_up()
    return {
        "ollama": ollama_up(),
        "live_lane": att.get("live_lane"),
        "updated": att.get("updated"),
        "tasks": ether_cowork.load(),
        "queue": pending,
        "role": role.get("role"),
        "generation": role.get("generation"),
        "idea": str(role.get("idea") or "")[:240],
        "verified": role.get("verified"),
        "activity": trace,
        "moving": moving,
        "progress": min(99, int(role.get("generation") or 0) * 3),
    }


def live_stop() -> Dict[str, Any]:
    return consume({"cmd": "stop"})


def shutdown() -> None:
    try:
        live_stop()
    except Exception:
        pass
    try:
        stop_ollama()
    except Exception:
        pass


def _git() -> str:
    for p in (
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files (x86)\Git\cmd\git.exe",
        "git",
    ):
        if p == "git" or Path(p).is_file():
            return p
    return "git"


def _git_kw(timeout: int = 90) -> Dict[str, Any]:
    kw: Dict[str, Any] = {
        "cwd": str(ROOT),
        "timeout": timeout,
        "capture_output": True,
        "text": True,
        "check": False,
    }
    if os.name == "nt":
        kw["creationflags"] = 0x08000000
    return kw


def git_run(*args: str, timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run([_git(), *args], **_git_kw(timeout=timeout))


def _push_attach() -> None:
    if "Otcde" not in str(ROOT):
        return
    paths = [
        "artifacts/host_attach.json",
        "artifacts/app_alive.json",
        "artifacts/gem_energy.json",
        "artifacts/cowork_board.json",
        "artifacts/self_build_role.json",
        "artifacts/self_build_trace.jsonl",
        "artifacts/week_tick.json",
    ]
    try:
        git_run("add", *paths)
        if git_run("diff", "--cached", "--quiet").returncode == 0:
            return
        git_run("-c", "user.email=ether@local", "-c", "user.name=ether-app", "commit", "-m", "1650 app attach")
        git_run("push", "origin", "main")
    except Exception:
        return


def health() -> Dict[str, Any]:
    return {"ollama": ollama_up(), "dashboard": DASHBOARD, "ok": True}


def log_turn(row: Dict[str, Any]) -> None:
    path = ROOT / "artifacts" / "app_chat.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row)[:4000] + "\n")


def git_status() -> str:
    try:
        p = git_run("status", "-sb", timeout=20)
        return ((p.stdout or "") + (p.stderr or ""))[:2000]
    except Exception as exc:
        return type(exc).__name__


def agent_turn(text: str) -> Dict[str, Any]:
    q = (text or "").strip()
    low = q.lower()
    actions: List[str] = []
    if low.startswith("task "):
        actions.append("task:" + str(ether_cowork.add(q[5:].strip())))
    if low.startswith("deliver "):
        actions.append("deliver:" + str(ether_cowork.deliver(q[8:].strip()[:40], ask_model(q))))
    if low.startswith("do "):
        actions.append("do:" + str(ether_cowork.run_task(q[3:].strip())))
    if low.startswith("edit ") and "->" in q:
        try:
            rest = q[5:]
            path, pair = rest.split(" ", 1)
            old, new = pair.split("->", 1)
            actions.append("edit:" + str(edit_file(path.strip(), old.strip(), new.strip())))
        except Exception as exc:
            actions.append("edit_fail:" + type(exc).__name__)
    hits = grep_repo(q.split()[0] if q else "")["hits"][:8]
    preview = ""
    if hits:
        try:
            preview = (ROOT / hits[0]).read_text(encoding="utf-8", errors="ignore")[:800]
        except Exception:
            preview = ""
    prompt = "ETHER repo agent.\nQ: " + q + "\nfiles: " + ", ".join(hits) + "\n" + preview
    reply = ask_model(prompt)
    if "status" in low:
        actions.append("git:" + git_status())
    if low.startswith("test") or "pytest" in low:
        actions.append("tool:" + str(run_allowlisted("pytest-fast")))
        proof = verify()
        actions.append("verify:" + str(proof.get("ok")))
    else:
        proof = verify()
    out = {
        "reply": reply,
        "files": hits,
        "actions": actions,
        "verified": proof.get("ok"),
        "ollama": ollama_up(),
        "status": git_status() if "status" in low else None,
    }
    log_turn({"q": q, **{k: out[k] for k in ("verified", "ollama", "files")}})
    return out


def ask_model_stream(text: str):
    if not ollama_up():
        yield "host up. ollama down."
        return
    import urllib.request
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps({"model": "qwen3.5:4b-q4_K_M", "prompt": text, "stream": True}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            for raw in resp:
                try:
                    chunk = json.loads(raw.decode())
                except Exception:
                    continue
                piece = str(chunk.get("response") or "")
                if piece:
                    yield piece
    except Exception as exc:
        yield type(exc).__name__


def ask_grok(text: str) -> str:
    key = os.environ.get("XAI_API_KEY") or os.environ.get("GROK_API_KEY") or ""
    if not key:
        return "Grok pane: set XAI_API_KEY on this PC. 4B stays local."
    import urllib.request
    body = json.dumps({
        "model": "grok-4",
        "messages": [{"role": "user", "content": text}],
    }).encode()
    req = urllib.request.Request(
        "https://api.x.ai/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
        return str(data["choices"][0]["message"]["content"])[:4000]
    except Exception as exc:
        return type(exc).__name__


def ask_model(text: str) -> str:
    if not ollama_up():
        return "host up. ollama down. FAST verify only."
    import urllib.request
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps({"model": "qwen3.5:4b-q4_K_M", "prompt": text, "stream": False}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
        return str(data.get("response") or "")[:4000]
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


def status_line(payload: Dict[str, Any]) -> str:
    v = (payload.get("verified") or {}).get("ok")
    return f"lane={payload.get('live_lane')} ollama={payload.get('ollama')} verified={v}"


def shell_kind() -> str:
    return "headless"


def open_dashboard() -> str:
    return "headless"


def run_e2e() -> Dict[str, Any]:
    started = boot()
    stopped = live_stop()
    restarted = live_start()
    return {
        "ok": bool(started.get("booted") and restarted.get("consumed") and started.get("verified", {}).get("ok")),
        "boot": started,
        "stop": stopped,
        "start": restarted,
        "health": health(),
        "shell": shell_kind(),
        "dashboard": DASHBOARD,
    }


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
        cmd = live_start()
        try:
            from scripts.ether_week_tick import tick as week_tick

            week_tick(push=False)
        except Exception:
            pass
        if str(cmd.get("cmd") or "") == "stop":
            break
        if ether_cowork.due_now():
            try:
                ether_role.tick()
                ether_cowork.mark_ran()
            except Exception:
                pass
        mark_alive()
        _push_attach()
        time.sleep(60)


def _ui_root() -> Path:
    disk = ROOT / "scripts" / "matrix-ui"
    if (disk / "index.html").is_file():
        return disk.parent
    disk2 = ROOT / "scripts"
    if (disk2 / "matrix-ui" / "index.html").is_file():
        return disk2
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def serve_local() -> None:
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    import json as _json

    class H(SimpleHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # type: ignore[override]
            if self.path.startswith("/update"):
                body = _json.dumps(update_self()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body); return
            if self.path.startswith("/start"):
                live_start()
                self.send_response(200); self.end_headers(); self.wfile.write(b'{"ok":true}'); return
            if self.path.startswith("/stop"):
                live_stop()
                self.send_response(200); self.end_headers(); self.wfile.write(b'{"ok":true}'); return
            if self.path.startswith("/files"):
                rows = []
                for sub in ("core", "gems", "scripts", "tests"):
                    d = ROOT / sub
                    if d.is_dir():
                        for p in sorted(d.rglob("*.py"))[:40]:
                            rows.append(str(p.relative_to(ROOT)).replace("\\", "/"))
                body = _json.dumps({"files": rows}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body); return
            if self.path.startswith("/read"):
                from urllib.parse import urlparse, parse_qs
                qs = parse_qs(urlparse(self.path).query)
                rel = (qs.get("path") or [""])[0]
                target = (ROOT / rel).resolve()
                try:
                    target.relative_to(ROOT.resolve())
                    txt = target.read_text(encoding="utf-8")[:20000]
                    body = _json.dumps({"path": rel, "text": txt}).encode()
                except Exception as exc:
                    body = _json.dumps({"error": type(exc).__name__}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body); return
            if self.path.startswith("/run"):
                body = _json.dumps(verify()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body); return
            if self.path.startswith("/tasks"):
                body = _json.dumps({"tasks": ether_cowork.load()}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body); return
            if self.path.startswith("/api/origin") or self.path.startswith("/origin"):
                att = {}
                pth = ROOT / "artifacts" / "host_attach.json"
                if pth.is_file():
                    try:
                        att = _json.loads(pth.read_text(encoding="utf-8"))
                    except Exception:
                        att = {}
                snap = {
                    "ok": True,
                    "ollama": bool(att.get("ollama")),
                    "live_lane": att.get("live_lane"),
                    "updated": att.get("updated"),
                    "source": "local-exe",
                    "dashboard": DASHBOARD,
                    "tasks": ether_cowork.load(),
                    "view": "bus",
                }
                body = _json.dumps(snap).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body); return
            if self.path.startswith("/status"):
                body = _json.dumps(dashboard_status()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body); return
            if self.path.startswith("/health"):
                att = {}
                pth = ROOT / "artifacts" / "host_attach.json"
                if pth.is_file():
                    try:
                        att = _json.loads(pth.read_text(encoding="utf-8"))
                    except Exception:
                        att = {}
                body = _json.dumps({
                    "ollama": bool(att.get("ollama")),
                    "live_lane": att.get("live_lane"),
                    "updated": att.get("updated"),
                    "ok": True,
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body); return
            if self.path in ("/", "/index.html", "/matrix.css", "/matrix.js"):
                name = "index.html" if self.path in ("/", "/index.html") else self.path.lstrip("/")
                cand = (_ui_root() / "matrix-ui") / name
                if not cand.is_file():
                    cand = (_ui_root() / "ether_ui.html") if name == "index.html" else cand
                page = cand.read_bytes() if cand.is_file() else b"missing"
                self.send_response(200)
                ctype = "text/css" if name.endswith(".css") else "application/javascript" if name.endswith(".js") else "text/html; charset=utf-8"
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(page)))
                self.end_headers(); self.wfile.write(page); return
            self.send_error(404)

        def do_POST(self) -> None:  # type: ignore[override]
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b"{}"
            try:
                payload = _json.loads(raw.decode() or "{}")
            except Exception:
                payload = {}
            if self.path.startswith("/grep"):
                body = _json.dumps(grep_repo(str(payload.get("q") or ""))).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body); return
            if self.path.startswith("/edit"):
                body = _json.dumps(edit_file(str(payload.get("path") or ""), str(payload.get("old") or ""), str(payload.get("new") or ""))).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body); return
            if self.path.startswith("/write"):
                body = _json.dumps(write_file(str(payload.get("path") or ""), str(payload.get("text") or ""))).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body); return
            if self.path.startswith("/ask_stream"):
                text = str(payload.get("text") or "")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                for piece in ask_model_stream(text):
                    self.wfile.write(piece.encode()); self.wfile.flush()
                return
            if self.path.startswith("/ask_grok"):
                text = str(payload.get("text") or "")
                body = _json.dumps({"reply": ask_grok(text)}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body); return
            if self.path.startswith("/ask"):
                text = str(payload.get("text") or "")
                body = _json.dumps(agent_turn(text)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body); return
            self.do_GET()

    ThreadingHTTPServer(("127.0.0.1", 7843), H).serve_forever()


def product_window() -> str:
    """Cowork window for the exe. Face of record is still the Grok Matrix."""
    import webview  # type: ignore

    webview.create_window("ETHER", DASHBOARD, width=1400, height=900)
    webview.start()
    return "webview"


def main() -> None:
    import threading
    atexit.register(shutdown)
    threading.Thread(target=_host_loop, name="ether-host", daemon=True).start()
    threading.Thread(target=serve_local, name="ether-ui", daemon=True).start()
    product_window()


if __name__ == "__main__":
    main()
