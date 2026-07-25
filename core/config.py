"""Load and validate @ETHER configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml
from pydantic import BaseModel, Field, ValidationError


class GrandidieriteConfig(BaseModel):
    allowed_imports: List[str] = Field(default_factory=list)
    forbidden_imports: List[str] = Field(default_factory=list)
    forbidden_patterns: List[str] = Field(default_factory=list)
    max_recursion_depth: int = 3
    sandbox_required: bool = True
    approval_required: bool = True
    tool_ttl_seconds: int = 604800
    max_tools_per_session: int = 5


class SandboxConfig(BaseModel):
    default_profile: str = "fast"
    memory_limit_mb: int = 2048
    cpu_limit: int = 2
    network: str = "disabled"
    read_only: bool = True


class OrchestratorConfig(BaseModel):
    max_retries: int = 3
    max_loops: int = 5
    default_timeout_seconds: int = 60


class ModelsConfig(BaseModel):
    primary: str = "qwen3-coder-next:32b-q4_k_m"
    router: str = "phi3:mini"
    embed: str = "nomic-embed-text"


class EtherConfig(BaseModel):
    grandidierite: GrandidieriteConfig = Field(default_factory=GrandidieriteConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)


def load_config(path: Path | None = None) -> EtherConfig:
    if path is None:
        path = Path(__file__).parent.parent / "config" / "manifest.yaml"
    if not path.exists():
        return EtherConfig()
    data: Dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    try:
        return EtherConfig(**data)
    except ValidationError as e:
        raise RuntimeError(f"Invalid manifest at {path}: {e}") from e
