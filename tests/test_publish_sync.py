"""Writer sync rebases. It must not drop a local app_alive commit."""
import subprocess
from pathlib import Path

from scripts.origin_publish import existing_paths, hard_reset_allowed, sync_writer


def test_hard_reset_blocked_when_ahead_or_dirty() -> None:
    assert hard_reset_allowed(local_ahead=0, dirty=False) is True
    assert hard_reset_allowed(local_ahead=1, dirty=False) is False
    assert hard_reset_allowed(local_ahead=0, dirty=True) is False


def test_existing_paths_skips_missing(tmp_path: Path) -> None:
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "app_alive.json").write_text("{}\n", encoding="utf-8")
    found = existing_paths(tmp_path)
    assert found == ["artifacts/app_alive.json"]


def test_sync_keeps_local_commit(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    origin = tmp_path / "origin.git"
    writer = tmp_path / "writer"
    other = tmp_path / "other"
    seed.mkdir()
    env = {
        **dict(**{k: v for k, v in __import__("os").environ.items() if k != "GIT_DIR"}),
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@local",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@local",
    }
    def git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, env=env, check=False)

    git(seed, "init")
    (seed / "README").write_text("base\n", encoding="utf-8")
    git(seed, "add", "README")
    git(seed, "commit", "-m", "base")
    git(seed, "branch", "-M", "main")
    subprocess.run(["git", "clone", "--bare", str(seed), str(origin)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(origin), str(writer)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(origin), str(other)], check=True, capture_output=True)
    (writer / "alive.txt").write_text("today\n", encoding="utf-8")
    git(writer, "add", "alive.txt")
    git(writer, "commit", "-m", "writer-alive")
    (other / "cloud.txt").write_text("tick\n", encoding="utf-8")
    git(other, "add", "cloud.txt")
    git(other, "commit", "-m", "cloud-tick")
    git(other, "push", "origin", "main")

    def runner(argv: list) -> subprocess.CompletedProcess:
        return subprocess.run(argv, cwd=str(writer), capture_output=True, text=True, env=env, check=False)

    row = sync_writer(writer, "git", runner)
    log = git(writer, "log", "--oneline").stdout
    assert row["hard_reset"] is False
    assert row["ok"] is True
    assert "writer-alive" in log
    assert "cloud-tick" in log


def test_writer_sources_do_not_hard_reset() -> None:
    for rel in ("scripts/origin_publish.py", "scripts/host_main.py", "scripts/ether_app.py"):
        text = Path(rel).read_text(encoding="utf-8")
        assert 'reset", "--hard"' not in text
        assert "reset --hard origin" not in text
