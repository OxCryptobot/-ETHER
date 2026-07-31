"""Real multi-file workflow under memory/scratch only."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "memory" / "scratch"

# Injected into the generation prompt for multi-file objectives.
# Must stay aligned with extract_file_blocks / run_multifile_cycle.
_GENERATION_ADDON = (
    "Multi-file format (required when more than one module is needed):\n"
    "# file: util.py\n"
    "<pure helpers with asserts>\n"
    "# file: main.py\n"
    "<entry that imports util and runs asserts>\n"
    "Rules: only .py names; no path escape; include asserts in entry; "
    "no markdown fences; no disk I/O outside these blocks.\n\n"
)


def generation_prompt_addon() -> str:
    """Directive the pipeline appends for multi-file objectives."""
    return _GENERATION_ADDON


def is_multifile_objective(objective: str) -> bool:
    o = (objective or "").lower()
    return bool(
        re.search(
            r"\b(multi[- ]?file|two files|three files|module a|module b|"
            r"refactor|package|across (modules|files)|split into)\b",
            o,
        )
        or "memory/scratch" in o
        or "# file:" in o
    )


def write_pair(files: Dict[str, str]) -> Dict[str, Any]:
    """Write name->content under scratch. Reject path escape. All-or-nothing."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    scratch = SCRATCH.resolve()
    written: List[str] = []
    backups: List[Tuple[Path, Optional[bytes]]] = []
    made_dirs: List[Path] = []

    def _rollback(error: str) -> Dict[str, Any]:
        for path, prior in reversed(backups):
            try:
                if prior is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(prior)
            except OSError:
                pass
        for d in reversed(made_dirs):
            try:
                d.rmdir()
            except OSError:
                pass
        return {"ok": False, "error": error}

    def _contained(path: Path) -> bool:
        try:
            return path.resolve().is_relative_to(scratch)
        except (OSError, ValueError, RuntimeError):
            return False

    for raw_name, content in (files or {}).items():
        name = str(raw_name).replace("\\", "/").strip().lstrip("/")
        if not name or ".." in Path(name).parts or Path(name).is_absolute():
            return _rollback("path escape")
        if not name.endswith(".py"):
            name = name + ".py"
        path = SCRATCH / name
        if not _contained(path):
            return _rollback("outside scratch")

        cur = SCRATCH
        for part in Path(name).parts[:-1]:
            cur = cur / part
            if cur.exists():
                if not cur.is_dir():
                    return _rollback("parent is not a directory")
                continue
            try:
                cur.mkdir()
            except OSError as e:
                return _rollback(f"mkdir failed: {e}")
            made_dirs.append(cur)

        if not _contained(path):
            return _rollback("outside scratch")

        try:
            prior = path.read_bytes() if path.is_file() else None
        except OSError:
            prior = None
        backups.append((path, prior))
        try:
            path.write_text(content if content is not None else "", encoding="utf-8")
        except OSError as e:
            return _rollback(f"write failed: {e}")
        written.append(str(path.relative_to(ROOT)))
    return {"ok": True, "written": written}


def extract_file_blocks(code: str) -> Dict[str, str]:
    """Parse markers: # file: foo.py ... # file: bar.py"""
    files: Dict[str, str] = {}
    if not code:
        return files
    parts = re.split(r"(?m)^#\s*file:\s*([\w./-]+)\s*$", code)
    if len(parts) < 3:
        return files
    it = iter(parts[1:])
    for name in it:
        body = next(it, "")
        files[name.strip()] = body.strip() + "\n"
    return files


def run_multifile_cycle(generated: str) -> Tuple[str, Dict[str, Any]]:
    """If multi-file markers present, write to scratch and build a runner string."""
    files = extract_file_blocks(generated)
    meta: Dict[str, Any] = {"multifile": bool(files)}
    if not files:
        return generated, meta
    w = write_pair(files)
    meta["write"] = w
    if not w.get("ok"):
        return generated, meta
    scratch_rel = SCRATCH.relative_to(ROOT).as_posix() + "/"
    written_rel = [
        str(p).replace("\\", "/").split(scratch_rel, 1)[-1] for p in (w.get("written") or [])
    ]
    if not written_rel:
        return generated, meta
    entry = None
    for cand in ("test_main.py", "test_app.py", "main.py", "app.py"):
        match = next((r for r in written_rel if Path(r).name == cand), None)
        if match:
            entry = match
            break
    if entry is None:
        entry = written_rel[0]
    payload = {
        str(Path(name).as_posix()): content
        for name, content in files.items()
        if content is not None
    }
    runner = (
        "import os, runpy, sys, tempfile\n"
        f"__ether_files = {payload!r}\n"
        "__ether_dir = tempfile.mkdtemp(prefix='ether_mf_')\n"
        "for __ether_name, __ether_src in __ether_files.items():\n"
        "    __ether_path = os.path.join(__ether_dir, __ether_name)\n"
        "    os.makedirs(os.path.dirname(__ether_path) or __ether_dir, exist_ok=True)\n"
        "    with open(__ether_path, 'w', encoding='utf-8') as __ether_fh:\n"
        "        __ether_fh.write(__ether_src)\n"
        "sys.path.insert(0, __ether_dir)\n"
        f"runpy.run_path(os.path.join(__ether_dir, {entry!r}), run_name='__main__')\n"
    )
    meta["entry"] = entry
    return runner, meta
