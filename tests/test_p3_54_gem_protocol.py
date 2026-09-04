"""p3_54: typed gem registry lists all 8 packages."""
from gems.protocol import GEMS, by_id, live_gems


def test_eight_gems():
    assert len(GEMS) == 8
    ids = {g.id for g in GEMS}
    assert "clear_quartz" in ids
    assert "selenite" in ids


def test_clear_quartz_is_live():
    g = by_id("clear_quartz")
    assert g is not None
    assert g.status == "live"
    assert any(x.id == "clear_quartz" for x in live_gems())


def test_grandidierite_gated():
    g = by_id("grandidierite")
    assert g is not None
    assert g.status == "gated"
