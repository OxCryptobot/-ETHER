"""Load and validate @ETHER configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class _StrictModel(BaseModel):
    """Reject unknown keys.

    pydantic's default is extra="ignore", so a typo in the manifest
    (`forbiden_patterns`) validated cleanly and produced an empty
    `forbidden_patterns` — i.e. the static-safety pattern list that
    black-tourmaline enforces was silently switched off.
    """

    model_config = ConfigDict(extra="forbid")


class GrandidieriteConfig(_StrictModel):
    allowed_imports: List[str] = Field(default_factory=list)
    forbidden_imports: List[str] = Field(default_factory=list)
    forbidden_patterns: List[str] = Field(default_factory=list)
    max_recursion_depth: int = 3
    sandbox_required: bool = True
    approval_required: bool = True
    tool_ttl_seconds: int = 604800
    max_tools_per_session: int = 5


class SandboxConfig(_StrictModel):
    default_profile: str = "fast"
    memory_limit_mb: int = 2048
    cpu_limit: int = 2
    network: str = "disabled"
    read_only: bool = True


class OrchestratorConfig(_StrictModel):
    max_retries: int = 3
    max_loops: int = 5
    default_timeout_seconds: int = 60


class ModelsConfig(_StrictModel):
    primary: str = "qwen3-coder-next:32b-q4_k_m"
    router: str = "phi3:mini"
    embed: str = "nomic-embed-text"


class EtherConfig(_StrictModel):
    grandidierite: GrandidieriteConfig = Field(default_factory=GrandidieriteConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)


def load_config(path: Path | None = None) -> EtherConfig:
    """Load config/manifest.yaml.

    Raises rather than degrading. A missing or unreadable manifest used to
    return a default `EtherConfig()`, whose `grandidierite.forbidden_patterns`
    is an empty list — so a typo'd path or a deleted file turned the security
    pattern list off with no signal at all. Every caller (`cli status`,
    `cli doctor`, `core.health_check.check_manifest`) already catches the
    exception and reports it, which is the loud behaviour that was wanted.
    """
    if path is None:
        path = Path(__file__).parent.parent / "config" / "manifest.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"manifest not found at {path} — refusing to run with default "
            f"(empty) security patterns"
        )
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise RuntimeError(f"Unreadable manifest at {path}: {e}") from e
    try:
        data: Any = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise RuntimeError(f"Unparseable manifest at {path}: {e}") from e
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise RuntimeError(
            f"Invalid manifest at {path}: expected a mapping, got {type(data).__name__}"
        )
    try:
        return EtherConfig(**data)
    except ValidationError as e:
        raise RuntimeError(f"Invalid manifest at {path}: {e}") from e
