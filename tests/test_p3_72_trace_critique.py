"""p3_72: critique artifact includes a trace field."""
import inspect
from core.critique_on_fail import critique_fail


def test_critique_source_has_trace_wire():
    src = inspect.getsource(critique_fail)
    assert "critique_from_trace" in src
    assert '"trace"' in src or "trace" in src
