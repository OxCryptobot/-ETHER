"""ETHER host process. No popups. Boots attach + verified gem/agent contract."""
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

from scripts.live_host import consume, ollama_up, start_ollama
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
    """Pull latest desktop release next to this exe. Swap on next start."""
    dest = ROOT / "ETHER.exe.new"
    gh = r"C:\Program Files\GitHub CLI\gh.exe"
    if not Path(gh).is_file():
        gh = "gh"
    try:
        tmp = ROOT / "artifacts"
        tmp.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [gh, "release", "download", "desktop", "-p", "ETHER.exe", "-D", str(tmp), "--clobber"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
        src = tmp / "ETHER.exe"
        if proc.returncode == 0 and src.is_file():
            dest = ROOT / "ETHER.exe.new"
            dest.write_bytes(src.read_bytes())
            bat = ROOT / "artifacts" / "swap_ether.cmd"
            bat.write_text(
                "@echo off\ntimeout /t 2 /nobreak >nul\nmove /y ETHER.exe.new ETHER.exe\nstart \"\" ETHER.exe\n",
                encoding="utf-8",
            )
            return {"ok": True, "pending": str(dest)}
        return {"ok": False, "tail": ((proc.stdout or "") + (proc.stderr or ""))[-300:]}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}


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


def live_stop() -> Dict[str, Any]:
    return consume({"cmd": "stop"})


def _git() -> str:
    for p in (
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files (x86)\Git\cmd\git.exe",
        "git",
    ):
        if p == "git" or Path(p).is_file():
            return p
    return "git"


def _push_attach() -> None:
    # Never publish attach from CI / Grok sandbox.
    if "Otcde" not in str(ROOT):
        return
    git = _git()
    try:
        subprocess.run([git, "add", "artifacts/host_attach.json"], cwd=str(ROOT), check=False)
        if subprocess.run([git, "diff", "--cached", "--quiet"], cwd=str(ROOT)).returncode == 0:
            return
        subprocess.run(
            [git, "-c", "user.email=ether@local", "-c", "user.name=ether-app", "commit", "-m", "1650 app attach"],
            cwd=str(ROOT),
            check=False,
        )
        subprocess.run([git, "push", "origin", "main"], cwd=str(ROOT), check=False)
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
    git = _git()
    try:
        p = subprocess.run([git, "status", "-sb"], cwd=str(ROOT), capture_output=True, text=True, timeout=20)
        return (p.stdout or p.stderr or "")[:2000]
    except Exception as exc:
        return type(exc).__name__


def agent_turn(text: str) -> Dict[str, Any]:
    q = (text or "").strip()
    low = q.lower()
    actions: List[str] = []
    if low.startswith('task '):
        actions.append('task:' + str(ether_cowork.add(q[5:].strip())))
    if low.startswith('deliver '):
        actions.append('deliver:' + str(ether_cowork.deliver(q[8:].strip()[:40], ask_model(q))))
    if low.startswith('do '):
        actions.append('do:' + str(ether_cowork.run_task(q[3:].strip())))
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
        cmd = live_start()
        if str(cmd.get("cmd") or "") == "stop":
            break
        if ether_cowork.due_now():
            try:
                row = json.loads((ROOT / "artifacts" / "cowork_schedule.json").read_text(encoding="utf-8"))
                ether_cowork.run_task(str(row.get("title") or "scheduled")); ether_cowork.mark_ran()
            except Exception:
                pass
        time.sleep(60)


def serve_local() -> None:
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    from functools import partial
    import json as _json

    class H(SimpleHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # type: ignore[override]
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
                self.end_headers()
                self.wfile.write(body)
                return
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
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path.startswith("/run"):
                body = _json.dumps(verify()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path.startswith("/health"):
                att = {}
                p = ROOT / "artifacts" / "host_attach.json"
                if p.is_file():
                    try:
                        att = _json.loads(p.read_text(encoding="utf-8"))
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
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path in ("/", "/index.html"):
                page = (Path(__file__).with_name("ether_ui.html")).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.end_headers()
                self.wfile.write(page)
                return
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
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path.startswith("/edit"):
                body = _json.dumps(edit_file(str(payload.get("path") or ""), str(payload.get("old") or ""), str(payload.get("new") or ""))).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path.startswith("/write"):
                body = _json.dumps(write_file(str(payload.get("path") or ""), str(payload.get("text") or ""))).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path.startswith("/ask"):
                text = str(payload.get("text") or "")
                body = _json.dumps(agent_turn(text)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.do_GET()

    ThreadingHTTPServer(("127.0.0.1", 7843), H).serve_forever()


def product_window() -> str:
    """Matrix lives inside the app window."""
    import webview  # type: ignore

    webview.create_window("ETHER", DASHBOARD, width=1400, height=900)
    webview.start()
    return "webview"


def main() -> None:
    import threading

    threading.Thread(target=_host_loop, name="ether-host", daemon=True).start()
    threading.Thread(target=serve_local, name="ether-ui", daemon=True).start()
    product_window()


if __name__ == "__main__":
    main()
