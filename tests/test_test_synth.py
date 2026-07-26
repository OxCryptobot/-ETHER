from core.test_synth import synthesize_asserts, has_assert


def test_synth_adds_assert():
    code = "def is_even(n):\n    return n % 2 == 0\n"
    out, mod = synthesize_asserts(code, "is_even")
    assert mod
    assert has_assert(out)


def test_synth_skips_if_present():
    code = "def f(x):\n    return x\nassert f(1)==1\n"
    out, mod = synthesize_asserts(code)
    assert not mod
