"""Minimal .env loader for @ETHER (no extra dependency).

Everything here feeds security-relevant flags (ETHER_SANDBOX_BACKEND,
ETHER_PATCH_LOOP, ETHER_AUTO_PROMOTE, ETHER_FLYWHEEL_PUSH), so a value this
parser mangles does not fail loudly — it silently reads as "not the safe
value I asked for". The parser therefore handles the three shapes an operator
actually writes: inline comments, `export KEY=VAL`, and quoted values.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _strip_inline_comment(value: str) -> str:
    """Drop a trailing ` # comment`, honouring quotes.

    A `#` only starts a comment when it is unquoted AND at the start of the
    value or preceded by whitespace, so values that legitimately contain a
    hash (`PASS=a#b`, `X="a # b"`) survive intact.
    """
    out: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(value):
        ch = value[i]
        if quote:
            out.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < len(value):
                out.append(value[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            out.append(ch)
        elif ch == "#" and (i == 0 or value[i - 1] in " \t"):
            break
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def parse_env_text(text: str) -> dict[str, str]:
    """Parse .env content into a dict (no os.environ side effects)."""
    out: dict[str, str] = {}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        # `export KEY=VAL` used to be stored under the literal key "export KEY"
        if line.startswith("export") and line[6:7] in (" ", "\t"):
            line = line[6:].lstrip()
        key, _, val = line.partition("=")
        key = key.strip()
        if not _KEY_RE.match(key):
            # junk (or a shell construct we do not understand) — never store it
            # under a bogus name where it would look loaded but read as unset
            continue
        out[key] = _unquote(_strip_inline_comment(val.strip()))
    return out


def load_dotenv(path: Path | None = None, override: bool = False) -> Path | None:
    """Load KEY=VALUE pairs from .env into os.environ.

    Does not modify variables already present in os.environ unless
    override=True — including variables set to the empty string, which the
    previous implementation quietly clobbered.

    When `path` is given explicitly it is used or nothing is: a tool that hands
    over an isolated env file must never be silently served the repo's
    production .env instead. The repo-root fallback applies only to the
    zero-argument call.

    Returns the path loaded, or None if missing.
    """
    if path is not None:
        env_path = Path(path)
        if not env_path.exists():
            return None
    else:
        env_path = Path.cwd() / ".env"
        if not env_path.exists():
            # try repo root relative to this file
            alt = Path(__file__).resolve().parents[1] / ".env"
            if not alt.exists():
                return None
            env_path = alt

    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError:
        return None

    for key, val in parse_env_text(text).items():
        if not override and key in os.environ:
            continue
        os.environ[key] = val
    return env_path
