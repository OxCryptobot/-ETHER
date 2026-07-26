"""Registry unit tests."""

from core.registry import GemRegistry


def test_missing_gem_returns_none():
    reg = GemRegistry()
    assert reg.get("nope") is None


def test_register_and_get():
    reg = GemRegistry()

    class Dummy:
        pass

    reg.register("dummy", Dummy())
    assert reg.get("dummy") is not None
