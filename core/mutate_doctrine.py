"""System-prompt suffix so 4B actually uses mutate tools."""
from __future__ import annotations

DOCTRINE = (
    "HARD FIX STRATEGY: after list_files call bug_comments, then "
    "anchor_edit or replace_once on the unique buggy line. "
    "Do not loop read_file. Do not rewrite whole files with write_file. "
    "Ledger: a.debit(amount) then b.credit(amount); total() returns s not s+s. "
    "Merge: return list copies; drain BOTH remainders after the main loop."
)


def suffix() -> str:
    return DOCTRINE
