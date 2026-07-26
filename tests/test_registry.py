from core.registry import GemRegistry, build_default_registry


def test_missing_gem_returns_none():
    reg = GemRegistry()
    assert reg.get("nope") is None


def test_list_gems_empty():
    reg = GemRegistry()
    assert reg.list_gems() == []


def test_list_gems_after_register():
    reg = GemRegistry()
    reg.register("clear-quartz", object())
    assert "clear-quartz" in reg.list_gems()


def test_default_registry_has_core_gems():
    reg = build_default_registry()
    names = set(reg.list_gems())
    for required in ("clear-quartz", "rose-quartz", "selenite", "black-tourmaline", "grandidierite"):
        assert required in names
