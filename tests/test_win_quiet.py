"""Git and Ollama must not open a window."""
from scripts.win_quiet import hidden_kwargs, quiet_env


def test_git_env_never_prompts() -> None:
    env = quiet_env({})
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GCM_INTERACTIVE"] == "Never"


def test_hidden_spawn_has_no_window_flag() -> None:
    kw = hidden_kwargs({})
    assert kw["stdin"] is not None
    if __import__("os").name == "nt":
        assert kw["creationflags"] & 0x08000000
        assert kw["startupinfo"].wShowWindow == 0


def test_ollama_does_not_spawn_when_process_exists() -> None:
    from pathlib import Path
    text = Path("scripts/live_host.py").read_text(encoding="utf-8")
    assert "ollama_process_up" in text
    assert "popen_hidden" in text
    assert "spawned_hidden" in text
