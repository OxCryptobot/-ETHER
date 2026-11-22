"""Host self-check (batch 5): broken imports on the writer path fail loudly, with the message.

    python -m scripts.host_selfcheck            # import check, JSON on stdout, rc 0/1
    python -m scripts.host_selfcheck --smoke    # + compile of every host-path module (post-pull smoke)

Why: the live host logged `plan_error: ImportError` every tick for 12 days (a publish had
deleted core.kernel.plan.heartbeat_plan) and nothing else showed it. host_main now runs
check_imports() at the start of every tick and writes the result into host_main.json
("selfcheck"); the supervisor runs --smoke after every pull that moved HEAD, before the
next writer pass, and (ETHER_PULL_ROLLBACK=1) rolls back locally to the last good commit.
Read-only: imports and compile() in memory, never writes the repo.
"""
from __future__ import annotations

import ast
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_HERE = Path(__file__).resolve().parents[1]

# Entry points of one writer pass and the modules the learning path imports lazily.
HOST_MODULES = (
    "scripts/host_main.py",
    "scripts/host_supervisor.py",
    "scripts/origin_publish.py",
    "scripts/live_edit_tx.py",
    "core/kernel/plan.py",
    "core/agent/sota.py",
    "core/agent/goal_source.py",
    "core/agent/outcome.py",
    "core/agent/bandit.py",
    "core/agent/fault_loc.py",
    "core/agent/multi_edit.py",
    "core/agent/refactor.py",
    "core/agent/goal_quality.py",
    "core/agent/react.py",
)
PKGS = ("core", "scripts", "gems")


def imports_of(root: Path, rel: str, pkgs: Tuple[str, ...] = PKGS) -> List[Tuple[str, Optional[str], int]]:
    """(module, name or None, line) for every repo import in the file, lazy ones included."""
    try:
        tree = ast.parse((Path(root) / rel).read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    out: List[Tuple[str, Optional[str], int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0 \
                and node.module.split(".")[0] in pkgs:
            for alias in node.names:
                out.append((node.module, None if alias.name == "*" else alias.name, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in pkgs:
                    out.append((alias.name, None, node.lineno))
    return out


def _err(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc)[:160]}"


def check_imports(root: Optional[Path] = None, rels: Tuple[str, ...] = HOST_MODULES,
                  pkgs: Tuple[str, ...] = PKGS) -> Dict[str, Any]:
    """Import every repo module the host path names and resolve every `from X import Y`."""
    root = Path(root or os.environ.get("ETHER_ROOT") or ROOT_HERE)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    broken: List[str] = []
    checked = 0
    seen: Dict[str, Any] = {}
    for rel in rels:
        if not (Path(root) / rel).is_file():
            broken.append(f"{rel}: missing")
            continue
        for mod, name, line in imports_of(root, rel, pkgs):
            checked += 1
            if mod not in seen:
                try:
                    seen[mod] = importlib.import_module(mod)
                except BaseException as exc:  # noqa: BLE001 - SystemExit from a module is a break too
                    seen[mod] = exc
            m = seen[mod]
            if isinstance(m, BaseException):
                broken.append(f"{rel}:{line} {mod}: {_err(m)}")
                continue
            if name and not hasattr(m, name):
                try:
                    importlib.import_module(f"{mod}.{name}")
                except BaseException as exc:  # noqa: BLE001
                    broken.append(f"{rel}:{line} {mod}.{name}: ImportError: cannot import name '{name}'"
                                  + ("" if isinstance(exc, ModuleNotFoundError) else f" ({_err(exc)})"))
    # one line per distinct break
    uniq = list(dict.fromkeys(broken))
    return {"ok": not uniq, "checked": checked, "modules": len(seen), "broken": uniq[:20],
            "n_broken": len(uniq)}


def compile_host(root: Optional[Path] = None, rels: Tuple[str, ...] = HOST_MODULES) -> Dict[str, Any]:
    """compile() (in memory) every host-path module and every repo module they import."""
    root = Path(root or os.environ.get("ETHER_ROOT") or ROOT_HERE)
    files = set(r for r in rels if (root / r).is_file())
    for rel in list(files):
        for mod, _name, _line in imports_of(root, rel):
            base = mod.replace(".", "/")
            for cand in (base + ".py", base + "/__init__.py"):
                if (root / cand).is_file():
                    files.add(cand)
                    break
    bad = []
    for rel in sorted(files):
        try:
            compile((root / rel).read_text(encoding="utf-8"), rel, "exec")
        except SyntaxError as exc:
            bad.append(f"{rel}:{exc.lineno} SyntaxError: {exc.msg}")
        except (OSError, ValueError) as exc:
            bad.append(f"{rel}: {_err(exc)}")
    return {"ok": not bad, "files": len(files), "bad": bad[:20]}


def smoke(root: Optional[Path] = None) -> Dict[str, Any]:
    comp = compile_host(root)
    imp = check_imports(root)
    return {"ok": bool(comp["ok"] and imp["ok"]), "compile": comp, "imports": imp}


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    out = smoke() if "--smoke" in args else check_imports()
    print(json.dumps(out, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
