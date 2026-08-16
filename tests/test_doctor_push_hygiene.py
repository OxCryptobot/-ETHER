"""CLI doctor includes push hygiene signal."""
from __future__ import annotations

import io
from contextlib import redirect_stdout


def test_doctor_mentions_hygiene():
    from scripts.ether_cli import main

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["doctor"])
    text = buf.getvalue()
    # INFO or WARNING line about hygiene / log
    assert "push_hygiene" in text or "host log" in text or "gitignore" in text
    # INFO-only hygiene should not alone force hard fail when host is up
    assert rc in (0, 1)
