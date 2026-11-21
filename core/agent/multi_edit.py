"""Transactional multi-target edits (batch 5, ETHER_MULTI_EDIT=1, default off).

Why: some failing tests can only pass when 2-3 places change together (a caller and
its callee in another file, a few listed import sites, a small module the test imports
that does not exist yet, a stray file that no longer parses). The single-function edit
path cannot express that, so those failures were dropped or tried forever on one half.

Rules (doctrine unchanged):
- at most MAX_TARGETS places, all named by the goal (never by the reply);
- protected paths (tests/, core/agent/, scripts/host_*, ...) are refused, as before;
- one FileTx over every touched path: any apply error, failing target/sibling test or
  regression reverts all of them (a new file is removed again);
- the prompt holds the error, the test and the current source of each place only,
  capped by the model context (2K/4K/8K);
- reward stays the honest gate: target + siblings pass, 0 regressions.
"""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MAX_TARGETS = 3
MAX_NEW_FILE_LINES = 150
MAX_FILE_LINES = 80          # whole-file rewrite only for small files that do not parse
ALT_MIN_RATIO = 0.7          # SBFL second suspect must score >= 70% of the first
MIN_SHARE = 300              # chars of current source per place below which a place is dropped
NO_MODULE = re.compile(r"No module named '([\w.]+)'")
SITE = re.compile(r"(?<![\w/.-])((?:core|gems|scripts|cli|tools|dashboard)/[\w/.-]+\.py):(\d+)\b(?!:)")
SYNTAX_FILE = re.compile(r'File "([^"]+\.py)", line (\d+)')
SYNTAX_KIND = re.compile(r"\b(?:SyntaxError|IndentationError|TabError)\b")


def enabled() -> bool:
    return os.getenv("ETHER_MULTI_EDIT", "0") == "1"


def _rel(root: Path, path: str) -> str:
    rel = path.replace("\\", "/")
    base = str(root).replace("\\", "/")
    if rel.startswith(base + "/"):
        rel = rel[len(base) + 1:]
    return rel


def _safe_rel(rel: str) -> bool:
    return bool(rel) and not rel.startswith("/") and ":" not in rel[:3] and ".." not in rel.split("/") \
        and rel.endswith(".py")


# ---------------------------------------------------------------- failure -> targets

def new_module_target(root: Path, text: str, test_src: str = "") -> Optional[Dict[str, Any]]:
    """ModuleNotFoundError for a repo module whose package exists -> one new small file."""
    from core.agent.goal_quality import protected

    m = NO_MODULE.search(text or "")
    if not m:
        return None
    dotted = m.group(1)
    top = dotted.split(".")[0]
    if top in ("tests", "test") or not (Path(root) / top / "__init__.py").is_file():
        return None  # third-party or not a repo package: still infra
    rel = dotted.replace(".", "/") + ".py"
    pkg = Path(root) / Path(rel).parent
    if protected(rel) or (Path(root) / rel).exists() or (Path(root) / rel[:-3]).is_dir():
        return None
    if not pkg.is_dir() or not ((pkg / "__init__.py").is_file() or pkg == Path(root) / top):
        return None
    names = []
    for mm in re.finditer(rf"from {re.escape(dotted)} import (?:\(([\w, \n]+)\)|([\w, ]+))", test_src or ""):
        listed = (mm.group(1) or mm.group(2) or "").replace("\n", ",")
        names += [n.strip().split(" as ")[0] for n in listed.split(",") if n.strip()]
    return {"file": rel, "symbol": "", "kind": "new_file", "names": sorted(set(names))[:8]}


def syntax_file_target(root: Path, text: str) -> Optional[Dict[str, Any]]:
    """A small non-protected repo file that does not parse -> whole-file rewrite target."""
    from core.agent.goal_quality import protected

    if not SYNTAX_KIND.search(text or ""):
        return None
    for m in SYNTAX_FILE.finditer(text or ""):
        rel = _rel(root, m.group(1))
        p = Path(root) / rel
        if not _safe_rel(rel) or protected(rel) or not p.is_file() or rel.startswith("tests/"):
            continue
        src = p.read_text(encoding="utf-8", errors="ignore")
        try:
            ast.parse(src)
            continue  # parses: not this failure's cause
        except SyntaxError:
            pass
        if len(src.splitlines()) <= MAX_FILE_LINES:
            return {"file": rel, "symbol": "", "kind": "file"}
    return None


def site_targets(root: Path, text: str) -> Tuple[List[Dict[str, Any]], str]:
    """`path.py:N` sites listed in an assertion message (not traceback frames) -> places.

    Returns (targets, reason). reason: "" ok, "too_many_sites", "no_sites"."""
    from core.agent.goal_quality import protected
    from core.agent.goal_source import _enclosing

    seen: List[Tuple[str, str]] = []
    for m in SITE.finditer(text or ""):
        rel, line = m.group(1), int(m.group(2))
        p = Path(root) / rel
        if not p.is_file() or protected(rel):
            continue
        sym = _enclosing(p, line)
        if not sym or sym.count(".") > 1:
            continue
        if (rel, sym) not in seen:
            seen.append((rel, sym))
    if len(seen) < 2:
        return [], "no_sites"
    if len(seen) > MAX_TARGETS:
        return [], "too_many_sites"
    return [{"file": r, "symbol": s, "kind": "function"} for r, s in seen], ""


def frame_alts(root: Path, text: str, primary: Tuple[str, str]) -> List[Dict[str, Any]]:
    """Callers in other non-protected files on the traceback (deepest first), as extra places."""
    from core.agent.goal_quality import protected
    from core.agent.goal_source import _enclosing, _repo_frames

    out: List[Dict[str, Any]] = []
    for rel, line in reversed(_repo_frames(root, text)):
        if protected(rel) or rel == primary[0]:
            continue
        sym = _enclosing(Path(root) / rel, line)
        if sym and sym.count(".") <= 1 and all(t["file"] != rel for t in out):
            out.append({"file": rel, "symbol": sym, "kind": "function"})
        if len(out) >= MAX_TARGETS - 1:
            break
    return out


def sbfl_alts(root: Path, nodeid: str, spectra: Optional[Dict[str, Any]], text: str,
              primary: Tuple[str, str]) -> List[Dict[str, Any]]:
    """Next suspects in other files scoring >= ALT_MIN_RATIO of the top suspect."""
    from core.agent import goal_source as gs
    from core.agent.goal_quality import protected

    if not spectra:
        return []
    ranked = gs.sbfl_ranked(root, nodeid, spectra, text)
    top = None
    out: List[Dict[str, Any]] = []
    for score, _o, rel, qual in ranked:
        if score < gs.SBFL_MIN:
            break
        if (rel, qual) == primary:
            top = score
            continue
        if top is None or score < ALT_MIN_RATIO * top or rel == primary[0]:
            continue
        if protected(rel) or qual.count(".") > 1 or not gs._is_function(root, rel, qual):
            continue
        if any(t["file"] == rel for t in out):
            continue
        out.append({"file": rel, "symbol": qual, "kind": "function"})
        if len(out) >= MAX_TARGETS - 1:
            break
    return out


def test_alts(root: Path, nodeid: str, primary: Tuple[str, str]) -> List[Dict[str, Any]]:
    """Other functions the failing test imports and calls, from other non-protected files."""
    from core.agent import goal_source as gs
    from core.agent.goal_quality import protected

    src = gs._test_source(root, nodeid)
    try:
        module_src = (Path(root) / nodeid.split("::", 1)[0]).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        module_src = ""
    out: List[Dict[str, Any]] = []
    for text in (src, module_src):
        for m in re.finditer(r"from ([A-Za-z_][\w.]*) import (?:\(([\w, \n]+)\)|([\w, ]+))", text):
            rel = gs.mod_rel(root, m.group(1))
            if rel == primary[0] or protected(rel) or not (Path(root) / rel).is_file():
                continue
            for name in [n.strip().split(" as ")[0] for n in (m.group(2) or m.group(3) or "").replace("\n", ",").split(",")]:
                if name and re.search(rf"\b{re.escape(name)}\(", src) and gs._is_function(root, rel, name) \
                        and all(t["file"] != rel for t in out):
                    out.append({"file": rel, "symbol": name, "kind": "function"})
        if len(out) >= MAX_TARGETS - 1:
            break
    return out[: MAX_TARGETS - 1]


def classify(root: Path, nodeid: str, text: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Multi/new-file goal for a failure the single-target classifier dropped, or (None, reason)."""
    from core.agent import goal_source as gs

    test_file = nodeid.split("::", 1)[0]
    test_src = gs._test_source(root, nodeid)
    try:
        module_src = (Path(root) / test_file).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        module_src = ""
    tgt = new_module_target(root, text, test_src + "\n" + module_src)
    via = "new_module"
    targets = [tgt] if tgt else []
    if not targets:
        tgt = syntax_file_target(root, text)
        via = "syntax_file"
        targets = [tgt] if tgt else []
    reason = ""
    if not targets:
        targets, reason = site_targets(root, text)
        via = "sites"
    if not targets:
        return None, reason or "no_sites"
    goal = gs._goal(root, nodeid, test_file, targets[0]["file"], targets[0]["symbol"] or "<module>",
                    targets[0]["kind"] == "new_file", text, via=via)
    if goal is None:
        return None, "protected_target"
    goal["targets"] = targets
    goal["multi"] = True
    return goal, "goal"


def targets_of(goal: Dict[str, Any], tries: int = 0) -> List[Dict[str, Any]]:
    """Places for this attempt: the goal's own list, or primary + alts once a single try failed."""
    if goal.get("targets"):
        return list(goal["targets"])[:MAX_TARGETS]
    if goal.get("alt_targets") and tries >= 1:
        prim = {"file": goal["file"], "symbol": goal["symbol"], "kind": "function"}
        return ([prim] + list(goal["alt_targets"]))[:MAX_TARGETS]
    return []


def trim_to_fit(root: Path, goal: Dict[str, Any], places: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop escalation places from the end until the reply cap can hold every place.
    A goal's own place list is all-or-nothing; fewer than 2 escalation places = single path."""
    if goal.get("targets"):
        return places if fits(root, places) else []
    out = list(places)
    while len(out) >= 2 and not fits(root, out):
        out = out[:-1]
    return out if len(out) >= 2 else []


# ---------------------------------------------------------------- prompt / reply size

def reply_tokens(root: Path, targets: List[Dict[str, Any]]) -> int:
    from core.agent import goal_source as gs

    need = 0
    for t in targets:
        if t["kind"] == "new_file":
            need += 220
        elif t["kind"] == "file":
            need += int(gs.est_tokens((Path(root) / t["file"]).read_text(encoding="utf-8", errors="ignore")) * 1.25)
        else:
            need += int(gs.est_tokens(gs._func_source(Path(root) / t["file"], t["symbol"])) * 1.25)
        need += 24
    return need + 48


def fits(root: Path, targets: List[Dict[str, Any]]) -> bool:
    from core.agent import goal_source as gs

    return bool(targets) and reply_tokens(root, targets) <= gs.reply_max()


def build_prompt(root: Path, goal: Dict[str, Any], targets: List[Dict[str, Any]], behaviour: Any = None,
                 feedback: str = "") -> Tuple[str, List[Dict[str, Any]]]:
    """(prompt, places kept). Error + test + current source of each place, within budget.

    Places that cannot get MIN_SHARE chars are dropped from the end (alts first); a goal
    whose own place list cannot fit returns ("", [])."""
    from core.agent import goal_source as gs
    from core.kernel.context_budget import context_char_budget, slice_to_budget

    root = Path(root)
    budget = context_char_budget()
    head = (f"Goal: make {goal.get('nodeid')} pass. The fix may need up to {len(targets)} places "
            "changed together; all are applied or none.\n"
            f"Error ({goal.get('error_kind')}):\n{str(goal.get('error') or '')[-400:]}\n")
    test = gs._test_source(root, goal["nodeid"])[:1000] if goal.get("nodeid") else ""
    tail = ("Reply with one block per place you change. Start each block with a line "
            "`# file: <path>` (a path listed above), then the complete new function "
            "(`def name(...)`, no class wrapper) or, for a whole file, the complete file. "
            "No markdown, no other paths.\n")
    addon = (getattr(behaviour, "prompt_addon", "") or "") + "\n" if behaviour is not None else ""
    parts = [head]
    if test:
        parts.append(f"Test:\n{test}\n")
    if feedback:
        parts.append(f"Your last try failed:\n{feedback[-300:]}\n")
    kept = list(targets)
    while kept:
        fixed = sum(len(p) for p in parts) + len(tail) + len(addon) + 60 * len(kept) + 40
        share = (budget - fixed) // len(kept)
        if share >= MIN_SHARE:
            break
        if goal.get("targets") and len(kept) <= len(goal["targets"]):
            return "", []
        kept = kept[:-1]
    if not kept or (len(kept) < 2 and not goal.get("targets")):
        return "", []
    blocks = []
    for t in kept:
        p = root / t["file"]
        if t["kind"] == "new_file":
            names = ", ".join(t.get("names") or []) or "(see the test)"
            blocks.append(f"### place: {t['file']} (new file, does not exist yet; the test imports: {names})\n")
            continue
        body = p.read_text(encoding="utf-8", errors="ignore")
        if t["kind"] == "file":
            cur = body
            label = f"### place: {t['file']} (whole file; it does not parse)\n"
        else:
            cur = gs._func_source(p, t["symbol"])
            label = f"### place: {t['file']} :: {t['symbol']} (current)\n"
        if len(cur) > share:
            cur = slice_to_budget(body, query=(t["symbol"] or "").split(".")[-1] or "def", cap=share)
        blocks.append(label + cur[:share] + "\n")
    prompt = "".join(parts) + "".join(blocks) + addon + tail
    return prompt[:budget], kept


# ---------------------------------------------------------------- reply -> edits -> one transaction

FILE_HDR = re.compile(r"^\s*#\s*file:\s*(\S+)\s*$", re.M)


def extract(reply: str, targets: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
    """([{"target", "function"|"source", "assigns"}], reason). Any block for a path that is
    not one of the places rejects the whole reply (the reply never picks what it may edit)."""
    from core.agent import goal_source as gs

    text = re.sub(r"```(?:python)?", "", (reply or "").replace("\r\n", "\n"))
    heads = list(FILE_HDR.finditer(text))
    if not heads:
        return [], "no `# file:` blocks"
    by_file = {t["file"]: t for t in targets}
    edits: List[Dict[str, Any]] = []
    for i, m in enumerate(heads):
        rel = m.group(1).strip("`'\"").replace("\\", "/")
        block = text[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)].strip("\n")
        t = by_file.get(rel)
        if t is None:
            return [], f"path not in the goal: {rel}"
        if any(e["target"]["file"] == rel for e in edits):
            return [], f"two blocks for {rel}"
        if t["kind"] in ("new_file", "file"):
            src = block.rstrip() + "\n"
            try:
                ast.parse(src)
            except SyntaxError as exc:
                return [], f"{rel}: syntax: {exc.msg}"
            limit = MAX_NEW_FILE_LINES if t["kind"] == "new_file" else max(MAX_FILE_LINES * 2, 40)
            if len(src.splitlines()) > limit:
                return [], f"{rel}: {len(src.splitlines())} lines > {limit}"
            edits.append({"target": t, "source": src})
        else:
            sub = {"file": rel, "symbol": t["symbol"]}
            edit = gs.extract_edit(block, sub)
            if not edit["function"]:
                return [], f"{rel}: no complete `def {t['symbol'].split('.')[-1]}`"
            edits.append({"target": t, **edit})
    return edits, ""


def apply(root: Path, edits: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Apply every edit inside one FileTx. On any error everything is reverted."""
    from core.agent import goal_source as gs
    from core.agent.goal_quality import protected
    from core.kernel.edit_tx import FileTx

    root = Path(root)
    rels = [e["target"]["file"] for e in edits]
    if not edits:
        return {"ok": False, "reason": "empty edit"}
    if len(edits) > MAX_TARGETS:
        return {"ok": False, "reason": f"too many places ({len(edits)} > {MAX_TARGETS})"}
    for rel in rels:
        if not _safe_rel(rel) or protected(rel):
            return {"ok": False, "reason": f"protected path {rel}"}
    tx = FileTx(root, rels).begin()
    try:
        for e in edits:
            t = e["target"]
            p = root / t["file"]
            if t["kind"] == "new_file":
                if p.exists():
                    raise ValueError(f"{t['file']} exists")
                if not p.parent.is_dir():
                    raise ValueError(f"package {p.parent.name} missing")
                p.write_text(e["source"], encoding="utf-8")
            elif t["kind"] == "file":
                if e["source"] == p.read_text(encoding="utf-8", errors="ignore"):
                    raise ValueError(f"{t['file']}: no change")
                p.write_text(e["source"], encoding="utf-8")
            else:
                res = gs.apply_edit(root, {"file": t["file"], "symbol": t["symbol"]},
                                    {"function": e["function"], "assigns": e.get("assigns") or {}})
                if not res.get("ok"):
                    raise ValueError(f"{t['file']}: {res.get('reason')}")
    except Exception as exc:
        tx.revert()
        return {"ok": False, "reason": str(exc)[:200]}
    return {"ok": True, "tx": tx, "files": tx.changed()}


def guard_suite(root: Path, goal: Dict[str, Any], targets: List[Dict[str, Any]]) -> List[str]:
    from core.agent import goal_source as gs

    files: List[str] = []
    for t in targets:
        for f in gs.guard_suite(root, {**goal, "file": t["file"]}):
            if f not in files:
                files.append(f)
    return files[: gs.MAX_AFFECTED * 2 + 3] if os.getenv("ETHER_GUARD_SUITE") != "full" else ["tests"]
