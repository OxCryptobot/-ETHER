import pytest
from core.registry import GemRegistry


def test_missing_gem_message():
    reg = GemRegistry()
    with pytest.raises(KeyError) as ei:
        reg.get("nope")
    assert "not registered" in str(ei.value)
