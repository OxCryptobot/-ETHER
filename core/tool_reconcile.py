"""Reconcile tools/quarantine vs tools/persistent.

- Unique → rename by functionality → promote to persistent
- Duplicate / near-duplicate → discard from quarantine
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
PERSISTENT = ROOT / "tools" / "persistent"
QUARANTINE = ROOT / "tools" / "quarantine"


def _promotion_gate(path: Path) -> Dict[str, Any]:
    """Safety gate a quarantined tool must clear before becoming trusted.

    Mirrors the checks `fabricate()` applies, so the reconcile path cannot be
    used to bypass them. Fails CLOSED: if a gate cannot be evaluated, the tool
    is not promoted.
    """
    import os

    if os.getenv("ETHER_AUTO_PROMOTE", "0") != "1":
        return {"ok": False, "reason": "ETHER_AUTO_PROMOTE=0"}

    try:
        code = path.read_text(encoding="utf-8")
    except Exception as e:
        return {"ok": False, "reason": f"unreadable: {e}"}

    try:
        from gems.grandidierite.fabricate import static_safety

        safety = static_safety(code)
        if not safety.get("ok"):
            return {"ok": False, "reason": f"static_safety: {safety.get('findings')}"}
    except Exception as e:
        return {"ok": False, "reason": f"static_safety unavailable: {e}"}

    try:
        from uuid import uuid4

        from core.registry import build_default_registry
        from core.schemas import BlackTourmalineRequest, Envelope

        res = build_default_registry().execute(
            Envelope(
                task_id=uuid4(),
                target_gem="black-tourmaline",
                payload=BlackTourmalineRequest(artifact=code, artifact_type="code"),
            )
        )
        if res.error or res.payload is None:
            return {"ok": False, "reason": "audit unavailable"}
        if not res.payload.approved:
            return {"ok": False, "reason": f"audit rejected: {res.payload.violations}"}
    except Exception as e:
        return {"ok": False, "reason": f"audit error: {e}"}

    return {"ok": True, "reason": ""}


def _discard_gate() -> Dict[str, Any]:
    """Gate for the DELETE half of reconcile.

    Only promotion was gated, so a daemon-scheduled reconcile with
    ETHER_AUTO_PROMOTE=0 was a pure deleter: it could remove quarantined tools
    but never keep any, quietly draining work the operator had not reviewed.
    Discarding now needs the same consent as promoting (or an explicit
    discard-only opt-in).
    """
    import os

    if (os.getenv("ETHER_AUTO_DISCARD", "") or "").strip() == "1":
        return {"ok": True, "reason": ""}
    if (os.getenv("ETHER_AUTO_PROMOTE", "0") or "").strip() == "1":
        return {"ok": True, "reason": ""}
    return {
        "ok": False,
        "reason": "ETHER_AUTO_PROMOTE=0 (set ETHER_AUTO_DISCARD=1 for discard-only)",
    }


REPORT_PATH = ROOT / "memory" / "tools" / "reconcile_latest.json"
LOG_PATH = ROOT / "memory" / "tools" / "reconcile.jsonl"
ARCHIVE = ROOT / "tools" / "archive"

# names that should never be auto-deleted from persistent
PROTECTED = {"_lib.py", "__init__.py"}


def _archive(path: Path) -> Path:
    """Move a discarded tool aside instead of unlink()ing it.

    Discard used to be an unrecoverable `unlink()` driven by a similarity
    heuristic; one bad fingerprint destroyed the only copy of a tool.
    """
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = ARCHIVE / f"{stamp}_{path.name}"
    i = 2
    while dest.exists():
        dest = ARCHIVE / f"{stamp}_{i}_{path.name}"
        i += 1
    shutil.move(str(path), str(dest))
    return dest


def _read(path: Path) -> Optional[str]:
    """Source text, or None when the file cannot be read.

    Returning "" for unreadable files made every unreadable file fingerprint
    identically (same empty-body hash), so similarity() scored them 1.0
    against each other and reconcile discarded them as duplicates.
    """
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None


def _norm_name(name: str) -> str:
    stem = Path(name).stem.lower()
    # strip timestamps like foo_20260726_123456
    stem = re.sub(r"_\d{8}_\d{6}$", "", stem)
    stem = re.sub(r"_v?\d+$", "", stem)
    stem = re.sub(r"[^a-z0-9_]+", "_", stem)
    return stem.strip("_") or "tool"


def _tokens(text: str) -> Set[str]:
    return set(re.findall(r"[a-z_][a-z0-9_]{2,}", (text or "").lower()))


def _fingerprint(path: Path) -> Dict[str, Any]:
    raw = _read(path)
    unreadable = raw is None or not (raw or "").strip()
    if unreadable:
        # unique, path-derived hash: two files with no usable content must
        # never look like duplicates of each other
        return {
            "path": str(path),
            "name": path.name,
            "norm": _norm_name(path.name),
            "funcs": [],
            "imports": [],
            "doc": "",
            "hash": "u_" + hashlib.sha256(str(path).encode("utf-8", "ignore")).hexdigest()[:13],
            "tokens": [],
            "size": 0,
            "unreadable": True,
        }
    src = raw or ""
    funcs: List[str] = []
    imports: List[str] = []
    doc = ""
    try:
        tree = ast.parse(src)
        doc = (ast.get_docstring(tree) or "")[:200]
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs.append(node.name)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    imports.extend(a.name.split(".")[0] for a in node.names)
                elif node.module:
                    imports.append(node.module.split(".")[0])
    except SyntaxError:
        pass
    # body without comments/blank for hash
    body = re.sub(r"#.*", "", src)
    body = re.sub(r"\s+", " ", body).strip()
    if body:
        h = hashlib.sha256(body.encode("utf-8", errors="ignore")).hexdigest()[:16]
    else:
        # comment-only file: no code to compare, so keep its hash unique
        h = "e_" + hashlib.sha256(str(path).encode("utf-8", "ignore")).hexdigest()[:13]
    return {
        "path": str(path),
        "name": path.name,
        "norm": _norm_name(path.name),
        "funcs": sorted(set(funcs))[:20],
        "imports": sorted(set(imports))[:20],
        "doc": doc,
        "hash": h,
        "tokens": list(_tokens(src))[:80],
        "size": len(src),
        "unreadable": False,
    }


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def similarity(fa: Dict[str, Any], fb: Dict[str, Any]) -> float:
    if fa.get("unreadable") or fb.get("unreadable"):
        # nothing was compared — never claim a match we cannot justify
        return 0.0
    if fa.get("hash") and fa["hash"] == fb.get("hash"):
        return 1.0
    score = 0.0
    if fa.get("norm") == fb.get("norm"):
        score += 0.35
    elif fa.get("norm") in fb.get("norm", "") or fb.get("norm") in fa.get("norm", ""):
        score += 0.2
    fa_f, fb_f = set(fa.get("funcs") or []), set(fb.get("funcs") or [])
    score += 0.30 * _jaccard(fa_f, fb_f)
    score += 0.15 * _jaccard(set(fa.get("imports") or []), set(fb.get("imports") or []))
    score += 0.20 * _jaccard(set(fa.get("tokens") or []), set(fb.get("tokens") or []))
    return round(min(1.0, score), 3)


def functional_name(fp: Dict[str, Any]) -> str:
    """Derive a stable snake_case name from functions/doc/norm."""
    funcs = [f for f in (fp.get("funcs") or []) if f not in {"main", "run", "execute"}]
    if funcs:
        base = funcs[0]
    else:
        base = fp.get("norm") or "tool"
    base = re.sub(r"[^a-z0-9_]+", "_", base.lower()).strip("_")
    # prefer verb-ish prefixes already present
    if not re.match(r"^(get|list|run|check|scan|parse|format|save|load|merge|find|count|assert)", base):
        # keep as-is; still valid
        pass
    if not base:
        base = f"tool_{fp.get('hash', 'x')[:6]}"
    return base[:48]


def _unique_persistent_name(desired: str) -> str:
    PERSISTENT.mkdir(parents=True, exist_ok=True)
    candidate = f"{desired}.py"
    if not (PERSISTENT / candidate).exists():
        return candidate
    for i in range(2, 50):
        candidate = f"{desired}_{i}.py"
        if not (PERSISTENT / candidate).exists():
            return candidate
    return f"{desired}_{fp_hash_fallback()}.py"


def fp_hash_fallback() -> str:
    return datetime.now(timezone.utc).strftime("%H%M%S")


def reconcile(
    *,
    promote_threshold: float = 0.82,
    dry_run: bool = False,
    max_promote: int = 20,
) -> Dict[str, Any]:
    """Scan quarantine; promote unique tools; discard duplicates."""
    PERSISTENT.mkdir(parents=True, exist_ok=True)
    QUARANTINE.mkdir(parents=True, exist_ok=True)

    pers_files = [p for p in PERSISTENT.glob("*.py") if p.name not in PROTECTED]
    quar_files = sorted(QUARANTINE.glob("*.py"), key=lambda p: p.stat().st_mtime)

    pers_fps = [_fingerprint(p) for p in pers_files]
    actions: List[Dict[str, Any]] = []
    promoted = 0
    discarded = 0
    kept = 0
    discard_gate = _discard_gate()

    def _discard(path: Path, action: Dict[str, Any]) -> str:
        """Archive one quarantined tool. Returns 'discarded' or 'kept'."""
        if not discard_gate["ok"]:
            action["action"] = "blocked_discard"
            action["blocked_by"] = discard_gate["reason"]
            return "kept"
        if dry_run:
            action["would_archive_to"] = str(ARCHIVE / path.name)
            return "discarded"
        try:
            action["archived_to"] = str(_archive(path))
            return "discarded"
        except Exception as e:
            action["action"] = "error"
            action["error"] = str(e)
            return "kept"

    for qpath in quar_files:
        qfp = _fingerprint(qpath)
        if qfp.get("unreadable"):
            actions.append(
                {
                    "file": qpath.name,
                    "action": "kept_unreadable",
                    "reason": "empty or unreadable — cannot be fingerprinted or compared",
                }
            )
            kept += 1
            continue
        best: Optional[Tuple[float, Dict[str, Any]]] = None
        for pfp in pers_fps:
            sim = similarity(qfp, pfp)
            if best is None or sim > best[0]:
                best = (sim, pfp)
        # also compare against other quarantine already decided this pass? use persistent only

        if best and best[0] >= promote_threshold:
            action = {
                "file": qpath.name,
                "action": "discard_duplicate",
                "similarity": best[0],
                "match": best[1].get("name"),
                "reason": f"near-duplicate of persistent {best[1].get('name')}",
            }
            if _discard(qpath, action) == "discarded":
                discarded += 1
            else:
                kept += 1
            actions.append(action)
            continue

        # unique → promote with functional name
        if promoted >= max_promote:
            actions.append(
                {
                    "file": qpath.name,
                    "action": "kept_limit",
                    "reason": "max_promote reached",
                }
            )
            kept += 1
            continue

        fname = functional_name(qfp)
        dest_name = _unique_persistent_name(fname)
        # if dest already functionally same norm as an existing persistent, discard instead
        dest_norm = _norm_name(dest_name)
        collision = next((p for p in pers_fps if p["norm"] == dest_norm), None)
        if collision and best and best[0] >= 0.55:
            action = {
                "file": qpath.name,
                "action": "discard_duplicate",
                "similarity": best[0] if best else 0.0,
                "match": collision.get("name"),
                "reason": f"functional name collides with {collision.get('name')}",
            }
            if _discard(qpath, action) == "discarded":
                discarded += 1
            else:
                kept += 1
            actions.append(action)
            continue

        action = {
            "file": qpath.name,
            "action": "promote",
            "as": dest_name,
            "functional_name": fname,
            "similarity_best": best[0] if best else 0.0,
            "nearest_persistent": best[1].get("name") if best else None,
        }
        # Promotion moves self-fabricated code into tools/persistent, where
        # run_tool executes it with sys.executable and the full inherited
        # environment. This used to be a pure dedup pass with NO safety gate,
        # driven by the daemon on a timer — which silently defeated
        # ETHER_AUTO_PROMOTE=0, the only knob the operator was given.
        gate = _promotion_gate(qpath)
        if not gate["ok"]:
            action["action"] = "blocked"
            action["blocked_by"] = gate["reason"]
            kept += 1
            actions.append(action)
            continue

        if not dry_run:
            try:
                dest = PERSISTENT / dest_name
                shutil.copy2(qpath, dest)
                qpath.unlink()
                pers_fps.append(_fingerprint(dest))
                promoted += 1
            except Exception as e:
                action["action"] = "error"
                action["error"] = str(e)
                kept += 1
        else:
            # A dry run must model the same state the real run would reach.
            # pers_fps was only extended in the non-dry branch, so later
            # quarantine files were compared against a persistent set missing
            # everything promoted earlier in the pass — under-reporting the
            # discards a real run would perform.
            pers_fps.append(
                dict(
                    qfp,
                    path=str(PERSISTENT / dest_name),
                    name=dest_name,
                    norm=_norm_name(dest_name),
                )
            )
            promoted += 1
        actions.append(action)

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "promote_threshold": promote_threshold,
        "quarantine_before": len(quar_files),
        "persistent_count": len(list(PERSISTENT.glob("*.py"))),
        "promoted": promoted,
        "discarded": discarded,
        "kept": kept,
        "actions": actions,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(report) + "\n")
    return report
