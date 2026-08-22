"""GPU metrics — nvidia-smi snapshot for GTX-class hosts.

Publishes artifacts/gpu_metrics.json. Wired into host_agent write_status
and Control Matrix KPI strip. Never blocks the poll loop on failure.

Hardware lock: GTX 1650 4GB — warn when VRAM used approaches capacity.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "gpu_metrics.json"

# VRAM soft warn threshold (MB) for 4GB cards
VRAM_WARN_MB = int(os.getenv("ETHER_GPU_VRAM_WARN_MB", "3500"))
TEMP_WARN_C = int(os.getenv("ETHER_GPU_TEMP_WARN_C", "85"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _nvidia_smi_path() -> Optional[str]:
    found = shutil.which("nvidia-smi")
    if found:
        return found
    # Common Windows install locations
    for candidate in (
        r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
        r"C:\Windows\System32\nvidia-smi.exe",
    ):
        if Path(candidate).is_file():
            return candidate
    return None


def _parse_float(val: str) -> Optional[float]:
    s = (val or "").strip().replace("%", "").replace("MiB", "").replace("W", "").strip()
    if not s or s.upper() in ("N/A", "[N/A]", "NA"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def sample() -> Dict[str, Any]:
    """One-shot GPU sample. Safe if nvidia-smi missing."""
    smi = _nvidia_smi_path()
    if not smi:
        return {
            "ok": False,
            "available": False,
            "error": "nvidia-smi not found",
            "updated": _now(),
        }
    query = (
        "name,utilization.gpu,utilization.memory,memory.used,memory.total,"
        "temperature.gpu,power.draw,power.limit"
    )
    try:
        r = subprocess.run(
            [
                smi,
                f"--query-gpu={query}",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "available": True, "error": "nvidia-smi timeout", "updated": _now()}
    except Exception as e:
        return {
            "ok": False,
            "available": True,
            "error": f"{type(e).__name__}: {e}",
            "updated": _now(),
        }

    if r.returncode != 0:
        return {
            "ok": False,
            "available": True,
            "error": (r.stderr or r.stdout or "nvidia-smi failed")[:300],
            "updated": _now(),
        }

    gpus: List[Dict[str, Any]] = []
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            continue
        name = parts[0]
        util = _parse_float(parts[1])
        mem_util = _parse_float(parts[2])
        mem_used = _parse_float(parts[3])
        mem_total = _parse_float(parts[4])
        temp = _parse_float(parts[5])
        power = _parse_float(parts[6]) if len(parts) > 6 else None
        power_limit = _parse_float(parts[7]) if len(parts) > 7 else None
        warn: List[str] = []
        if mem_used is not None and mem_used >= VRAM_WARN_MB:
            warn.append(f"vram_high:{mem_used:.0f}MB")
        if temp is not None and temp >= TEMP_WARN_C:
            warn.append(f"temp_high:{temp:.0f}C")
        gpus.append(
            {
                "name": name,
                "util_gpu_pct": util,
                "util_mem_pct": mem_util,
                "mem_used_mb": mem_used,
                "mem_total_mb": mem_total,
                "temp_c": temp,
                "power_w": power,
                "power_limit_w": power_limit,
                "warn": warn,
            }
        )

    if not gpus:
        return {
            "ok": False,
            "available": True,
            "error": "no GPU rows parsed",
            "raw": (r.stdout or "")[:200],
            "updated": _now(),
        }

    primary = gpus[0]
    return {
        "ok": True,
        "available": True,
        "updated": _now(),
        "n": len(gpus),
        "primary": primary,
        "gpus": gpus,
        "util_gpu_pct": primary.get("util_gpu_pct"),
        "mem_used_mb": primary.get("mem_used_mb"),
        "mem_total_mb": primary.get("mem_total_mb"),
        "temp_c": primary.get("temp_c"),
        "name": primary.get("name"),
        "warn": primary.get("warn") or [],
        "vram_warn_mb": VRAM_WARN_MB,
        "temp_warn_c": TEMP_WARN_C,
    }


def publish() -> Dict[str, Any]:
    """Sample + write artifacts/gpu_metrics.json."""
    payload = sample()
    try:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    except Exception as e:
        payload["write_error"] = f"{type(e).__name__}: {e}"
    return payload


def snapshot_for_status() -> Dict[str, Any]:
    """Compact dict safe to embed in host_agent_status.json."""
    full = publish()
    if not full.get("ok"):
        return {
            "ok": False,
            "available": bool(full.get("available")),
            "error": full.get("error"),
            "updated": full.get("updated"),
        }
    return {
        "ok": True,
        "available": True,
        "name": full.get("name"),
        "util_gpu_pct": full.get("util_gpu_pct"),
        "mem_used_mb": full.get("mem_used_mb"),
        "mem_total_mb": full.get("mem_total_mb"),
        "temp_c": full.get("temp_c"),
        "warn": full.get("warn") or [],
        "updated": full.get("updated"),
    }


if __name__ == "__main__":
    print(json.dumps(publish(), indent=2))
