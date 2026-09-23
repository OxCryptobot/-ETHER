from scripts.host_main import _pid_alive

def test_dead_pid_is_not_alive() -> None:
    assert _pid_alive(0) is False
    assert _pid_alive(2**30) is False
