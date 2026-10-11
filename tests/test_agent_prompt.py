from core.kernel.agent_prompt import SYSTEM, messages


def test_the_prompt_fits_a_4b_and_speaks_the_parser() -> None:
    assert len(SYSTEM) < 500
    assert "READ:" in SYSTEM
    assert "complete function" in SYSTEM
    for leaked in ("return a + b", "s[0] + s[-1]", "return 'ada'", "hi ada"):
        assert leaked not in SYSTEM
    sent = messages("Failing cases:\nends")
    assert sent[0]["role"] == "system"
    assert sent[1] == {"role": "user", "content": "Failing cases:\nends"}
