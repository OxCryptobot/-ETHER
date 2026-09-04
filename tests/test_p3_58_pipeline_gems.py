"""p3_58: every protocol gem resolves on the live GemRegistry; Pipeline.run annotates."""
import inspect

from core.loop.gem_step import annotate_all
from core.pipeline import Pipeline
from core.registry import build_default_registry
from gems.protocol import GEMS, registry_key


def test_registry_key_hyphen():
    assert registry_key("rose_quartz") == "rose-quartz"
    assert registry_key("selenite") == "selenite"


def test_all_protocol_gems_registered():
    names = set(build_default_registry().list_gems())
    missing = []
    for gem in GEMS:
        key = registry_key(gem.id)
        if key not in names and gem.id not in names:
            missing.append(gem.id)
    assert missing == [], missing


def test_annotate_all_covers_stages():
    rows = annotate_all()
    assert len(rows) >= 8
    assert any(r["gem"] == "clear_quartz" and r["status"] == "live" for r in rows)
    assert any(r["key"] == "rose-quartz" for r in rows)


def test_pipeline_run_source_calls_annotate_all():
    src = inspect.getsource(Pipeline.run)
    assert "annotate_all" in src
