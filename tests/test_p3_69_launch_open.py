"""p3_69: launch OPEN. No gem remains status=gated."""
from gems.protocol import GEMS


def test_no_gem_gated():
    gated = [g.id for g in GEMS if g.status == "gated"]
    assert gated == [], gated


def test_grandidierite_partial_not_gated():
    g = next(x for x in GEMS if x.id == "grandidierite")
    assert g.status == "partial"
