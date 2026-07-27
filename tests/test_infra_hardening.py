"""Regressions for the infrastructure layer: scratch containment, queue
robustness, .env parsing, manifest loading, liveness probes, repair templates
and tool reconciliation.

Every test here failed against the code as it was; each one names the concrete
failure it prevents rather than restating the implementation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


# --------------------------------------------------------------------------
# core/multifile.py — scratch containment
# --------------------------------------------------------------------------


def test_write_pair_rejects_symlink_escape_from_scratch(tmp_path, monkeypatch):
    """A prefix test let a symlink inside scratch land files outside it.

    `str(path.resolve()).startswith(str(SCRATCH))` is satisfied by any sibling
    whose name merely extends the prefix (memory/scratch_evil), which is
    exactly where a symlink placed in scratch resolves to.
    """
    from core import multifile

    scratch = tmp_path / "scratch"
    outside = tmp_path / "scratch_evil"
    scratch.mkdir()
    outside.mkdir()
    (scratch / "evil").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(multifile, "SCRATCH", scratch)
    monkeypatch.setattr(multifile, "ROOT", tmp_path)

    res = multifile.write_pair({"evil/pwned.py": "print('escaped')"})

    assert res["ok"] is False
    assert res["error"] == "outside scratch"
    assert not (outside / "pwned.py").exists(), "write landed outside scratch"


def test_write_pair_creates_subdirectories_instead_of_raising(tmp_path, monkeypatch):
    """`extract_file_blocks` accepts "pkg/mod.py", so it must be writable.

    write_pair raised FileNotFoundError out of the call instead of returning
    the {"ok": False} contract its caller checks.
    """
    from core import multifile

    scratch = tmp_path / "scratch"
    monkeypatch.setattr(multifile, "SCRATCH", scratch)
    monkeypatch.setattr(multifile, "ROOT", tmp_path)

    res = multifile.write_pair({"pkg/mod.py": "VALUE = 1\n"})

    assert res["ok"] is True
    assert (scratch / "pkg" / "mod.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_write_pair_rolls_back_earlier_files_on_rejection(tmp_path, monkeypatch):
    """A mid-loop return used to leave earlier files on disk."""
    from core import multifile

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(multifile, "SCRATCH", scratch)
    monkeypatch.setattr(multifile, "ROOT", tmp_path)
    (scratch / "existing.py").write_text("ORIGINAL = 1\n", encoding="utf-8")

    res = multifile.write_pair(
        {
            "first.py": "A = 1\n",
            "existing.py": "OVERWRITTEN = 1\n",
            "../escape.py": "B = 2\n",
        }
    )

    assert res["ok"] is False
    assert res["error"] == "path escape"
    assert not (scratch / "first.py").exists(), "new file survived a failed batch"
    assert (scratch / "existing.py").read_text(encoding="utf-8") == "ORIGINAL = 1\n"


def test_multifile_runner_targets_the_file_that_was_written(tmp_path, monkeypatch):
    """Entry selection must keep the subdirectory, not just the basename."""
    from core import multifile

    scratch = tmp_path / "scratch"
    monkeypatch.setattr(multifile, "SCRATCH", scratch)
    monkeypatch.setattr(multifile, "ROOT", tmp_path)

    runner, meta = multifile.run_multifile_cycle(
        "# file: pkg/main.py\nprint('hi')\n"
    )

    assert meta["write"]["ok"] is True
    assert meta["entry"] == "pkg/main.py"
    # The runner must NOT reference a host path. The Docker sandbox mounts
    # nothing and runs --read-only, so a host path made every multifile run
    # die with FileNotFoundError and be scored as a code failure. The runner
    # embeds the sources and materialises them inside the sandbox instead.
    assert str(scratch) not in runner
    assert "pkg/main.py" in runner
    assert "tempfile" in runner and "runpy" in runner


# --------------------------------------------------------------------------
# core/batch_queue.py — malformed priority
# --------------------------------------------------------------------------


@pytest.fixture()
def isolated_queue(tmp_path, monkeypatch):
    from core import batch_queue as bq

    monkeypatch.setattr(bq, "QUEUE_PATH", tmp_path / "batch_queue.json")
    monkeypatch.setattr(bq, "HIST_PATH", tmp_path / "bq" / "history.jsonl")
    monkeypatch.setattr(bq, "LOCK_PATH", tmp_path / "bq" / ".queue.lock")
    return bq


@pytest.mark.parametrize("bad_priority", [None, "high", [], {}])
def test_enqueue_survives_a_malformed_priority_already_in_the_queue(
    isolated_queue, bad_priority
):
    """`int(x.get("priority", 100))` raised TypeError/ValueError in the sort.

    `autonomy.enqueue_failure` swallows exceptions, so one bad row stopped
    every failure requeue silently and permanently.
    """
    bq = isolated_queue
    bq.save_queue({"pending": [{"id": 1, "title": "bad", "priority": bad_priority}], "done": []})

    item = bq.enqueue(kind="pipeline", title="new", objective="x", priority=10)

    assert item["id"] == 2
    pending = bq.load_queue()["pending"]
    assert [p["title"] for p in pending] == ["new", "bad"], "sort dropped or misordered rows"


def test_seed_smoke_survives_a_malformed_priority(isolated_queue):
    bq = isolated_queue
    bq.save_queue({"pending": [{"id": 7, "title": "junk", "priority": "urgent"}], "done": []})

    out = bq.seed_smoke(force=True)

    assert out["ok"] is True and out["seeded"] == 4
    assert len(bq.load_queue()["pending"]) == 5


def test_enqueue_never_writes_a_non_int_priority(isolated_queue):
    bq = isolated_queue
    bq.save_queue({"pending": [], "done": []})

    item = bq.enqueue(kind="pipeline", title="t", objective="x", priority="nope")

    assert item["priority"] == 100
    assert isinstance(json.loads((bq.QUEUE_PATH).read_text())["pending"][0]["priority"], int)


# --------------------------------------------------------------------------
# core/dotenv.py — security flags must survive parsing
# --------------------------------------------------------------------------


@pytest.fixture()
def env_sandbox(monkeypatch):
    """Swap os.environ for a copy: loading a .env here must not leak sideways."""
    copy = dict(os.environ)
    monkeypatch.setattr(os, "environ", copy)
    return copy


def test_inline_comment_does_not_disable_an_explicit_security_flag(tmp_path, env_sandbox):
    """"docker # force container" != "docker", so the backend fell back to auto.

    That silently forfeits the explicit-docker no-downgrade guarantee.
    """
    from core.dotenv import load_dotenv

    env = tmp_path / ".env"
    env.write_text(
        "ETHER_SANDBOX_BACKEND=docker # force container\n"
        "ETHER_PATCH_LOOP=0  # host git apply stays off\n"
        "ETHER_AUTO_PROMOTE=0\t# no auto trust\n"
        "ETHER_FLYWHEEL_PUSH=0 # never push\n",
        encoding="utf-8",
    )
    for key in (
        "ETHER_SANDBOX_BACKEND",
        "ETHER_PATCH_LOOP",
        "ETHER_AUTO_PROMOTE",
        "ETHER_FLYWHEEL_PUSH",
    ):
        env_sandbox.pop(key, None)

    assert load_dotenv(env) == env
    assert os.environ["ETHER_SANDBOX_BACKEND"] == "docker"
    assert os.environ["ETHER_PATCH_LOOP"] == "0"
    assert os.environ["ETHER_AUTO_PROMOTE"] == "0"
    assert os.environ["ETHER_FLYWHEEL_PUSH"] == "0"


def test_comment_stripping_keeps_hashes_that_belong_to_the_value(tmp_path, env_sandbox):
    from core.dotenv import load_dotenv

    env = tmp_path / ".env"
    env.write_text(
        'ETHER_T_QUOTED="a # b"\n'
        "ETHER_T_TIGHT=pa#ssword\n"
        "ETHER_T_SQ='x # y' # trailing\n",
        encoding="utf-8",
    )
    for key in ("ETHER_T_QUOTED", "ETHER_T_TIGHT", "ETHER_T_SQ"):
        env_sandbox.pop(key, None)

    load_dotenv(env)

    assert os.environ["ETHER_T_QUOTED"] == "a # b"
    assert os.environ["ETHER_T_TIGHT"] == "pa#ssword"
    assert os.environ["ETHER_T_SQ"] == "x # y"


def test_export_prefix_is_stripped(tmp_path, env_sandbox):
    """`export KEY=VAL` was stored under the literal key "export KEY"."""
    from core.dotenv import load_dotenv

    env = tmp_path / ".env"
    env.write_text("export ETHER_T_EXPORTED=1\n", encoding="utf-8")
    env_sandbox.pop("ETHER_T_EXPORTED", None)

    load_dotenv(env)

    assert os.environ.get("ETHER_T_EXPORTED") == "1"
    assert "export ETHER_T_EXPORTED" not in os.environ


def test_missing_explicit_path_does_not_fall_back_to_the_repo_env(tmp_path):
    """A tool handing over an isolated env file got the production one."""
    from core.dotenv import load_dotenv

    repo_env = Path(__file__).resolve().parents[1] / ".env"
    result = load_dotenv(tmp_path / "does_not_exist.env")

    assert result is None, f"fell back to {result} (repo .env is {repo_env})"


def test_override_false_does_not_clobber_an_empty_env_var(tmp_path, env_sandbox):
    """The docstring promises existing vars are preserved; "" is existing."""
    from core.dotenv import load_dotenv

    env_sandbox["ETHER_T_EMPTY"] = ""
    env = tmp_path / ".env"
    env.write_text("ETHER_T_EMPTY=from_file\n", encoding="utf-8")

    load_dotenv(env, override=False)
    assert os.environ["ETHER_T_EMPTY"] == ""

    load_dotenv(env, override=True)
    assert os.environ["ETHER_T_EMPTY"] == "from_file"


# --------------------------------------------------------------------------
# core/config.py — a broken manifest must not silently disable the rules
# --------------------------------------------------------------------------


def test_missing_manifest_is_loud_instead_of_returning_empty_patterns(tmp_path):
    """A default EtherConfig has forbidden_patterns == [] — no security rules."""
    from core.config import load_config

    with pytest.raises(Exception) as exc:
        load_config(tmp_path / "nope.yaml")
    assert "nope.yaml" in str(exc.value)


def test_typo_in_a_security_key_is_rejected(tmp_path):
    """extra="ignore" made `forbiden_patterns` vanish with no error."""
    from core.config import load_config

    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "grandidierite:\n  forbiden_patterns:\n    - \"eval\\\\(\"\n", encoding="utf-8"
    )

    with pytest.raises(RuntimeError) as exc:
        load_config(manifest)
    assert "forbiden_patterns" in str(exc.value)


def test_unparseable_and_non_mapping_manifests_raise_runtime_error(tmp_path):
    """yaml.YAMLError / TypeError escaped raw from a function promising RuntimeError."""
    from core.config import load_config

    broken = tmp_path / "broken.yaml"
    broken.write_text("grandidierite: [unclosed\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        load_config(broken)

    not_a_mapping = tmp_path / "list.yaml"
    not_a_mapping.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        load_config(not_a_mapping)


def test_real_manifest_still_loads_with_strict_extras():
    from core.config import load_config

    cfg = load_config()
    assert cfg.grandidierite.forbidden_patterns, "security patterns are empty"


# --------------------------------------------------------------------------
# core/infra_status.py — probes must describe this machine
# --------------------------------------------------------------------------


def test_runner_probe_is_not_windows_only(monkeypatch):
    """The probe lived inside `if os.name == "nt"`, so on Linux it was always
    False -> an unconditional warn -> `overall` could never be "ok"."""
    from core import infra_status

    monkeypatch.setattr(infra_status, "_port_open", lambda *a, **k: True)
    monkeypatch.setattr(infra_status, "_pid_alive", lambda p: True)
    monkeypatch.setattr(infra_status, "_hb_age_s", lambda p: 1.0)
    monkeypatch.setattr(
        infra_status, "_docker_probe", lambda: {"cli": True, "daemon": True, "endpoint": "x"}
    )
    monkeypatch.setattr(infra_status, "_runner_listener_up", lambda: False)
    monkeypatch.setattr(infra_status, "_runner_expected", lambda: False)

    infra = infra_status.collect_infra()

    runner_alerts = [a for a in infra["alerts"] if "runner" in a["text"].lower()]
    assert runner_alerts and all(a["level"] != "warn" for a in runner_alerts)
    assert infra["overall"] == "ok", infra["alerts"]


def test_runner_probe_warns_only_when_a_runner_is_installed(monkeypatch):
    from core import infra_status

    monkeypatch.setattr(infra_status, "_port_open", lambda *a, **k: True)
    monkeypatch.setattr(infra_status, "_pid_alive", lambda p: True)
    monkeypatch.setattr(infra_status, "_hb_age_s", lambda p: 1.0)
    monkeypatch.setattr(
        infra_status, "_docker_probe", lambda: {"cli": True, "daemon": True, "endpoint": "x"}
    )
    monkeypatch.setattr(infra_status, "_runner_listener_up", lambda: False)
    monkeypatch.setenv("ETHER_GITHUB_RUNNER", "1")

    infra = infra_status.collect_infra()

    assert infra["runner"]["expected"] is True
    assert any(a["level"] == "warn" and "runner" in a["text"].lower() for a in infra["alerts"])


def test_ollama_probe_dials_the_configured_host_not_localhost(monkeypatch):
    """Only the PORT was parsed from OLLAMA_BASE_URL; the host was hardcoded
    to 127.0.0.1, so a remote Ollama was reported up off a local listener."""
    from core import infra_status

    seen = []

    def _fake_port_open(host, port, timeout=0.4):
        seen.append((host, port))
        return host != "10.0.0.9"

    monkeypatch.setattr(infra_status, "_port_open", _fake_port_open)
    monkeypatch.setattr(infra_status, "_pid_alive", lambda p: True)
    monkeypatch.setattr(infra_status, "_hb_age_s", lambda p: 1.0)
    monkeypatch.setattr(
        infra_status, "_docker_probe", lambda: {"cli": True, "daemon": True, "endpoint": "x"}
    )
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://10.0.0.9:11434")

    infra = infra_status.collect_infra()

    assert ("10.0.0.9", 11434) in seen
    assert infra["ollama"]["host"] == "10.0.0.9"
    assert infra["ollama"]["up"] is False
    assert infra["overall"] == "down"


def test_host_port_parsing_handles_the_shapes_operators_write():
    from core.infra_status import _host_port

    assert _host_port("http://localhost:11434", "127.0.0.1", 11434) == ("localhost", 11434)
    assert _host_port("http://box.lan", "127.0.0.1", 11434) == ("box.lan", 11434)
    assert _host_port("https://ollama.example.com", "127.0.0.1", 11434) == (
        "ollama.example.com",
        443,
    )
    assert _host_port("box.lan:6333", "127.0.0.1", 6333) == ("box.lan", 6333)
    assert _host_port("", "127.0.0.1", 6333) == ("127.0.0.1", 6333)


def test_docker_and_qdrant_are_probed(monkeypatch):
    """Both are hard dependencies and neither had a probe at all."""
    from core import infra_status

    monkeypatch.setattr(infra_status, "_pid_alive", lambda p: True)
    monkeypatch.setattr(infra_status, "_hb_age_s", lambda p: 1.0)
    monkeypatch.setattr(
        infra_status,
        "_docker_probe",
        lambda: {"cli": False, "daemon": False, "endpoint": "sock"},
    )
    monkeypatch.setattr(infra_status, "_port_open", lambda host, port, timeout=0.4: port != 6333)
    monkeypatch.setenv("ETHER_SANDBOX_BACKEND", "docker")
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")

    infra = infra_status.collect_infra()

    assert infra["docker"]["daemon"] is False and infra["docker"]["required"] is True
    assert infra["qdrant"]["up"] is False and infra["qdrant"]["port"] == 6333
    texts = " | ".join(a["text"] for a in infra["alerts"])
    assert "Docker" in texts and "Qdrant" in texts
    assert infra["overall"] == "down", "an explicit docker backend with no daemon is not 'ok'"


# --------------------------------------------------------------------------
# core/failure_graph.py — repair templates were unreachable
# --------------------------------------------------------------------------


@pytest.fixture(autouse=False)
def isolated_graph(tmp_path, monkeypatch):
    from core import failure_graph

    monkeypatch.setattr(failure_graph, "GRAPH_PATH", tmp_path / "failure_graph.json")
    return failure_graph


@pytest.mark.parametrize(
    "stderr",
    [
        "SyntaxError: invalid syntax",
        "NameError: name 'x' is not defined",
        "ModuleNotFoundError: No module named 'requests'",
        "AssertionError",
        "TypeError: unsupported operand",
        "ValueError: invalid literal",
        "Timeout: exceeded 60s",
    ],
)
def test_every_classified_kind_has_a_reachable_template(isolated_graph, stderr):
    """TEMPLATES was keyed "syntax"/"name"/... while classify_stderr returns
    "SyntaxError"/"NameError"/..., so every lookup fell through to runtime."""
    from core.repair import classify_stderr

    kind = classify_stderr(stderr)["kind"]
    hint = isolated_graph.repair_hint(stderr)

    assert kind in isolated_graph.TEMPLATES
    assert hint == isolated_graph.TEMPLATES[kind]
    assert hint != isolated_graph.TEMPLATES["runtime"]


def test_repair_hint_accepts_a_bare_kind_string(isolated_graph):
    """core/experience.py calls repair_hint(fail_kind), not repair_hint(stderr)."""
    assert isolated_graph.repair_hint("SyntaxError") == isolated_graph.TEMPLATES["SyntaxError"]
    assert isolated_graph.repair_hint("Timeout") == isolated_graph.TEMPLATES["Timeout"]
    assert isolated_graph.repair_hint("runtime") == isolated_graph.TEMPLATES["runtime"]
    # legacy short keys still resolve
    assert isolated_graph.repair_hint("syntax") == isolated_graph.TEMPLATES["SyntaxError"]


def test_observe_refreshes_a_stale_runtime_template(isolated_graph):
    """Nodes persisted before the key alignment carry the generic template."""
    node = isolated_graph.observe("TypeError: bad operand")
    assert node["template"] == isolated_graph.TEMPLATES["TypeError"]

    data = json.loads(isolated_graph.GRAPH_PATH.read_text(encoding="utf-8"))
    sig = node["signature"]
    data["nodes"][sig]["template"] = isolated_graph.TEMPLATES["runtime"]
    isolated_graph.GRAPH_PATH.write_text(json.dumps(data), encoding="utf-8")

    assert isolated_graph.repair_hint("TypeError: bad operand") == (
        isolated_graph.TEMPLATES["TypeError"]
    )


# --------------------------------------------------------------------------
# core/tool_reconcile.py — deletion was ungated and unrecoverable
# --------------------------------------------------------------------------


@pytest.fixture()
def reconcile_env(tmp_path, monkeypatch):
    from core import tool_reconcile as tr

    monkeypatch.setattr(tr, "PERSISTENT", tmp_path / "persistent")
    monkeypatch.setattr(tr, "QUARANTINE", tmp_path / "quarantine")
    monkeypatch.setattr(tr, "ARCHIVE", tmp_path / "archive")
    monkeypatch.setattr(tr, "REPORT_PATH", tmp_path / "report.json")
    monkeypatch.setattr(tr, "LOG_PATH", tmp_path / "reconcile.jsonl")
    (tmp_path / "persistent").mkdir()
    (tmp_path / "quarantine").mkdir()
    monkeypatch.delenv("ETHER_AUTO_DISCARD", raising=False)
    monkeypatch.setenv("ETHER_AUTO_PROMOTE", "0")
    return tr


def _duplicate_pair(tr):
    src = "def widget_alpha(x):\n    return x + 1\n"
    (tr.PERSISTENT / "widget_alpha.py").write_text(src, encoding="utf-8")
    (tr.QUARANTINE / "widget_alpha_20260101_010101.py").write_text(src, encoding="utf-8")


def test_discard_is_gated_like_promotion(reconcile_env):
    """Only promotion was gated, so a daemon-scheduled reconcile with
    ETHER_AUTO_PROMOTE=0 was a pure deleter."""
    tr = reconcile_env
    _duplicate_pair(tr)

    report = tr.reconcile()

    assert report["discarded"] == 0
    assert (tr.QUARANTINE / "widget_alpha_20260101_010101.py").exists()
    blocked = [a for a in report["actions"] if a["action"] == "blocked_discard"]
    assert blocked and "ETHER_AUTO_PROMOTE" in blocked[0]["blocked_by"]


def test_discard_archives_instead_of_unlinking(reconcile_env, monkeypatch):
    """Discard was `unlink()` on a similarity heuristic — unrecoverable."""
    tr = reconcile_env
    monkeypatch.setenv("ETHER_AUTO_DISCARD", "1")
    _duplicate_pair(tr)

    report = tr.reconcile()

    assert report["discarded"] == 1
    assert not (tr.QUARANTINE / "widget_alpha_20260101_010101.py").exists()
    archived = list(tr.ARCHIVE.glob("*widget_alpha_20260101_010101.py"))
    assert archived, "discarded tool was destroyed, not archived"
    assert "def widget_alpha" in archived[0].read_text(encoding="utf-8")


def test_unreadable_files_do_not_fingerprint_as_duplicates_of_each_other(reconcile_env):
    """_read swallowed errors to "", so two unreadable files hashed identically
    -> similarity 1.0 -> both discarded as duplicates."""
    tr = reconcile_env
    a = tr._fingerprint(tr.QUARANTINE / "gone_a.py")
    b = tr._fingerprint(tr.QUARANTINE / "gone_b.py")

    assert a["hash"] != b["hash"]
    assert tr.similarity(a, b) == 0.0


def test_empty_quarantine_file_is_kept_not_discarded(reconcile_env, monkeypatch):
    tr = reconcile_env
    monkeypatch.setenv("ETHER_AUTO_DISCARD", "1")
    (tr.QUARANTINE / "empty_one.py").write_text("", encoding="utf-8")
    (tr.QUARANTINE / "empty_two.py").write_text("\n\n", encoding="utf-8")

    report = tr.reconcile()

    assert report["discarded"] == 0
    assert report["kept"] == 2
    assert {a["action"] for a in report["actions"]} == {"kept_unreadable"}
    assert len(list(tr.QUARANTINE.glob("*.py"))) == 2


def test_dry_run_reports_the_same_counts_as_a_real_run(tmp_path, monkeypatch):
    """pers_fps.append only ran in the non-dry branch, so a dry run compared
    later files against a persistent set missing everything promoted earlier
    and under-reported the deletions a real run performs."""
    from core import tool_reconcile as tr

    src = "def widget_beta(x):\n    return x * 2\n"

    def _setup(root: Path):
        monkeypatch.setattr(tr, "PERSISTENT", root / "persistent")
        monkeypatch.setattr(tr, "QUARANTINE", root / "quarantine")
        monkeypatch.setattr(tr, "ARCHIVE", root / "archive")
        monkeypatch.setattr(tr, "REPORT_PATH", root / "report.json")
        monkeypatch.setattr(tr, "LOG_PATH", root / "reconcile.jsonl")
        (root / "persistent").mkdir(parents=True)
        (root / "quarantine").mkdir(parents=True)
        (root / "quarantine" / "aaa_20260101_010101.py").write_text(src, encoding="utf-8")
        (root / "quarantine" / "bbb_20260102_020202.py").write_text(src, encoding="utf-8")

    monkeypatch.setenv("ETHER_AUTO_PROMOTE", "1")

    _setup(tmp_path / "dry")
    dry = tr.reconcile(dry_run=True)
    assert sorted(p.name for p in tr.QUARANTINE.glob("*.py")) == [
        "aaa_20260101_010101.py",
        "bbb_20260102_020202.py",
    ], "dry run touched the filesystem"

    _setup(tmp_path / "real")
    real = tr.reconcile(dry_run=False)

    assert (dry["promoted"], dry["discarded"], dry["kept"]) == (
        real["promoted"],
        real["discarded"],
        real["kept"],
    )
    assert dry["discarded"] == 1
