"""Week autonomy tick — gem_energy + role stamp + board + trace. FAST-safe."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def _root() -> Path:
    env = os.environ.get("ETHER_ROOT")
    if env and (Path(env) / "scripts").is_dir():
        return Path(env).resolve()
    win = Path(r"C:\Users\Otcde\ETHER")
    if (win / "scripts").is_dir():
        return win.resolve()
    return Path(__file__).resolve().parents[1]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ollama() -> bool:
    try:
        from scripts.live_host import ollama_up

        return bool(ollama_up())
    except Exception:
        return False


def tick(push: bool = False) -> Dict[str, Any]:
    root = _root()
    art = root / "artifacts"
    art.mkdir(parents=True, exist_ok=True)

    ollama = _ollama()
    gem = "rose-quartz" if ollama else "citrine"
    energy: Dict[str, Any] = {}
    try:
        from core.gem_energy import bump

        energy = bump(gem, job="week_tick")
    except Exception as exc:
        energy = {"ok": False, "error": type(exc).__name__}

    board = [
        {"id": "week_ollama", "title": "Keep Ollama 4B attached on the 1650", "status": "open" if not ollama else "live"},
        {"id": "week_git", "title": "Exe pulls origin and pushes attach/energy/role", "status": "open"},
        {"id": "week_matrix", "title": "Matrix stays READ-ONLY and polls origin", "status": "live"},
        {"id": "week_energy", "title": "gem_energy.json stamped every tick", "status": "live"},
        {"id": "week_loop", "title": "Idle FAST week_tick while Grok is dark", "status": "live"},
    ]
    (art / "cowork_board.json").write_text(json.dumps({"tasks": board}, indent=2) + "\n", encoding="utf-8")

    role_path = art / "self_build_role.json"
    idea = "week tick: stamp energy + board. 4B speaks only when ollama is up."
    if ollama:
        try:
            from scripts.ether_role import tick as role_tick

            role = role_tick()
        except Exception as exc:
            role = {"role": "self_build_cowork", "ok": False, "error": type(exc).__name__, "idea": idea}
    else:
        prev: Dict[str, Any] = {}
        if role_path.is_file():
            try:
                prev = json.loads(role_path.read_text(encoding="utf-8"))
            except Exception:
                prev = {}
        gen = int(prev.get("generation") or 0) + 1
        role = {
            "role": "self_build_cowork",
            "ok": True,
            "backend": "fast_week" if not ollama else "ollama_local",
            "idea": idea,
            "verified": False,
            "ts": _now(),
            "generation": gen,
            "ollama": ollama,
        }
        role_path.write_text(json.dumps(role, indent=2) + "\n", encoding="utf-8")

    trace = art / "self_build_trace.jsonl"
    with trace.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ts": _now(),
                    "idea": idea,
                    "generation": role.get("generation"),
                    "verified": bool(role.get("verified")),
                    "ollama": ollama,
                    "last_gem": energy.get("last_gem") if isinstance(energy, dict) else gem,
                }
            )[:800]
            + "\n"
        )

    row = {
        "ok": True,
        "ts": _now(),
        "ollama": ollama,
        "last_gem": energy.get("last_gem") if isinstance(energy, dict) else gem,
        "generation": role.get("generation"),
        "board_n": len(board),
    }
    (art / "week_tick.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    if push:
        _push(root)
    return row


def _push(root: Path) -> None:
    if "Otcde" not in str(root):
        return
    import subprocess

    git = "git"
    for p in (r"C:\Program Files\Git\cmd\git.exe", r"C:\Program Files (x86)\Git\cmd\git.exe"):
        if Path(p).is_file():
            git = p
            break
    flags = 0x08000000 if os.name == "nt" else 0
    paths = [
        "artifacts/gem_energy.json",
        "artifacts/cowork_board.json",
        "artifacts/self_build_role.json",
        "artifacts/self_build_trace.jsonl",
        "artifacts/week_tick.json",
        "artifacts/host_attach.json",
    ]
    try:
        kw: Dict[str, Any] = {"cwd": str(root), "timeout": 90}
        if flags:
            kw["creationflags"] = flags
        subprocess.run([git, "add", *paths], **kw)
        if subprocess.run([git, "diff", "--cached", "--quiet"], **kw).returncode == 0:
            return
        subprocess.run(
            [git, "-c", "user.email=ether@local", "-c", "user.name=ether-week", "commit", "-m", "week tick: energy + role"],
            **kw,
        )
        subprocess.run([git, "push", "origin", "main"], **kw)
    except Exception:
        return


if __name__ == "__main__":
    print(json.dumps(tick(), indent=2))
