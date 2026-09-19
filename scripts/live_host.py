"""Consume host_command. Start Ollama when the binary is on this machine."""
from __future__ import annotations
import json, os, shutil, subprocess, time, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

TARGET_MODEL = os.getenv("ETHER_OLLAMA_MODEL", "qwen3.5:4b-q4_K_M")

def _root() -> Path:
    env = os.environ.get("ETHER_ROOT")
    return Path(env) if env else Path(__file__).resolve().parents[1]

def ollama_up() -> bool:
    url = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=2) as res:
            return int(getattr(res, "status", 200) or 200) < 400
    except (urllib.error.URLError, TimeoutError, OSError):
        return False

def ollama_bin() -> Optional[str]:
    env = (os.getenv("OLLAMA_BIN") or os.getenv("ETHER_OLLAMA_BIN") or "").strip()
    if env and Path(env).is_file():
        return env
    which = shutil.which("ollama")
    if which:
        return which
    home = Path.home()
    local = os.getenv("LOCALAPPDATA") or str(home / "AppData" / "Local")
    for p in (
        Path(local) / "Programs" / "Ollama" / "ollama.exe",
        home / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe",
        Path(r"C:\Users\Otcde\AppData\Local\Programs\Ollama\ollama.exe"),
        Path(r"C:\Program Files\Ollama\ollama.exe"),
        Path("/usr/local/bin/ollama"),
        Path("/usr/bin/ollama"),
    ):
        try:
            if p.is_file():
                return str(p)
        except OSError:
            continue
    return None

def list_models() -> List[str]:
    url = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=3) as res:
            data = json.loads(res.read().decode("utf-8", errors="replace") or "{}")
        return [str((row or {}).get("name") or "") for row in (data.get("models") or []) if (row or {}).get("name")]
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return []

def write_probe(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    models = list_models() if ollama_up() else []
    row: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "up": ollama_up(),
        "bin": ollama_bin(),
        "models": models[:20],
        "target": TARGET_MODEL,
        "has_target": any(TARGET_MODEL in m or m.startswith(TARGET_MODEL.split(":")[0]) for m in models),
        "writer": "exe" if os.name == "nt" else "observe",
    }
    if extra:
        row.update(extra)
    path = _root() / "artifacts" / "ollama_probe.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
    return row

_OLLAMA_PROC = None

def start_ollama() -> bool:
    global _OLLAMA_PROC
    if ollama_up():
        write_probe({"started": False, "reason": "already_up"})
        return True
    bin_ = ollama_bin()
    if not bin_:
        write_probe({"started": False, "reason": "bin_missing"})
        return False
    try:
        kwargs: Dict[str, Any] = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "env": os.environ.copy(), "cwd": str(Path(bin_).parent)}
        kwargs["env"]["PATH"] = str(Path(bin_).parent) + os.pathsep + kwargs["env"].get("PATH", "")
        if os.name == "nt":
            kwargs["creationflags"] = 0x08000000
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            kwargs["startupinfo"] = si
        _OLLAMA_PROC = subprocess.Popen([bin_, "serve"], **kwargs)
    except OSError as exc:
        write_probe({"started": False, "reason": "spawn_fail", "error": type(exc).__name__})
        return False
    for _ in range(24):
        time.sleep(0.5)
        if ollama_up():
            write_probe({"started": True, "reason": "spawned"})
            return True
    write_probe({"started": False, "reason": "timeout_api"})
    return ollama_up()

def stop_ollama() -> None:
    global _OLLAMA_PROC
    proc = _OLLAMA_PROC
    _OLLAMA_PROC = None
    if proc and proc.poll() is None:
        try:
            proc.terminate()
        except Exception:
            pass

def ensure_model(pull: bool = False) -> Dict[str, Any]:
    if not ollama_up() and not start_ollama():
        row = write_probe({"ensure": "down"})
        row["ok"] = False
        return row
    models = list_models()
    has = any(TARGET_MODEL in m or m.startswith("qwen3.5:4b") for m in models)
    if has or not pull:
        row = write_probe({"ensure": "present" if has else "missing_no_pull"})
        row["ok"] = True
        row["has_target"] = has
        return row
    bin_ = ollama_bin()
    if not bin_:
        row = write_probe({"ensure": "bin_missing"})
        row["ok"] = False
        return row
    try:
        kw: Dict[str, Any] = {"timeout": 1800, "capture_output": True, "text": True}
        if os.name == "nt":
            kw["creationflags"] = 0x08000000
        subprocess.run([bin_, "pull", TARGET_MODEL], **kw)
    except Exception as exc:
        row = write_probe({"ensure": "pull_fail", "error": type(exc).__name__})
        row["ok"] = False
        return row
    row = write_probe({"ensure": "pulled"})
    row["ok"] = bool(row.get("has_target") or ollama_up())
    return row

def consume(command: Dict[str, Any] | None = None) -> Dict[str, Any]:
    ollama = start_ollama()
    root = _root()
    out = root / "artifacts" / "host_attach.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    prev: Dict[str, Any] = {}
    if out.is_file():
        try:
            prev = json.loads(out.read_text(encoding="utf-8"))
        except Exception:
            prev = {}
    try:
        from core.kernel.attach import attach_payload
        may, observed = attach_payload(ollama_up=bool(ollama), prev=prev, cmd=str((command or {}).get("cmd") or prev.get("cmd") or "attach"))
        if not may:
            write_probe({"attach": "observe"})
            observed = dict(observed)
            observed["path"] = str(out)
            return observed
    except Exception:
        if os.name != "nt":
            write_probe({"attach": "observe_fallback"})
            row = dict(prev)
            row.update({"consumed": False, "clobber": False, "note": "observe only. exe owns attach.", "writer": prev.get("writer") or "exe", "path": str(out)})
            return row
    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "ok": True,
        "fast_lane": "matrix-worker",
        "live_lane": "ollama_4b" if ollama else "grok_bus",
        "living_ok": True,
        "ollama": ollama,
        "grok_bus": not ollama,
        "cmd": (command or {}).get("cmd") or "attach",
        "consumed": True,
        "clobber": False,
        "note": "Starts ollama serve when binary exists. Else grok_bus.",
        "writer": "exe",
        "bin": ollama_bin(),
    }
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    payload["path"] = str(out)
    write_probe({"attach": "write", "ollama": ollama})
    return payload

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    path = root / "artifacts" / "host_command.json"
    body = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"cmd": "attach"}
    print(json.dumps(consume(body), indent=2))
