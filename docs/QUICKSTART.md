# @ETHER Quickstart (third party)

Local-first coding agent. **Verified execution** (sandbox before you see code), **modular gems**, **controlled evolution** (tools stay quarantined until gated).

## Hardware (reference host)

| Resource | Minimum for product path |
|----------|--------------------------|
| GPU | GTX 1650 4GB (or CPU-only, slower) |
| RAM | 12 GB |
| Model | ≤4B class — default `qwen3.5:4b` |
| OS | Windows 10/11 x64 or Linux |

Do **not** pull 7B/14B on 4GB VRAM hosts.

## Prerequisites

1. **Python 3.11+**
2. **Ollama** with models:
   ```bash
   ollama pull qwen3.5:4b
   ollama pull nomic-embed-text
   ```
3. **Docker** (recommended) for sandbox isolation + Qdrant:
   ```bash
   docker compose -f deploy/docker-compose.qdrant.yml up -d
   ```
   Without Docker: set `ETHER_SANDBOX_BACKEND=local` (weaker isolation).

## Install

### Windows (PowerShell)

```powershell
git clone https://github.com/OxCryptobot/-ETHER.git
cd -ETHER
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
# Edit .env if your ollama tag differs: ollama list
ether doctor
```

### Linux / macOS

```bash
git clone https://github.com/OxCryptobot/-ETHER.git
cd -ETHER
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
ether doctor
```

`ether doctor` must show sandbox_ok, ollama, manifest, registry green. Qdrant optional but required for Citrine memory.

## First run

```bash
ether run "write a python function is_even(n) that returns True for even integers; include asserts"
```

Expect: plan → code → sandbox exit=0 → audit → critique → memory_save.

Repo-grounded:

```bash
ether run "in this repo, list the public functions in core/patterns.py as a python dict with one-line docstrings; include asserts"
```

Multi-file:

```bash
# optional deterministic arm
export ETHER_FORCE_STRATEGY=multifile   # Windows: $env:ETHER_FORCE_STRATEGY="multifile"
ether run "multi-file package: # file: util.py with add(a,b); # file: main.py imports add and asserts add(2,3)==5"
```

## Safe defaults (do not change unless you mean it)

| Variable | Default | Meaning |
|----------|---------|---------|
| `ETHER_AUTO_PROMOTE` | `0` | Fabricated tools stay in quarantine |
| `ETHER_AUTO_FABRICATE_ON_FAIL` | `0` | No auto tool spawn on fail streak |
| `ETHER_FLYWHEEL_PUSH` | unset | No auto git push |
| `ETHER_WARM_SANDBOX` | `0` | No shared warm container |
| `ETHER_PRIMARY_MODEL` | `qwen3.5:4b` | Host-class model |

## Public CLI surface

| Command | Purpose |
|---------|---------|
| `ether doctor` | Health + evolution metrics |
| `ether run "..."` | Full verified pipeline |
| `ether plan "..."` | Plan only |
| `ether fabricate --name X --purpose Y [--stub-only]` | Tool gen → quarantine |
| `ether promote FILE.py` | Operator-gated promote |
| `ether tool-list` / `ether tool-run` | Persistent tools |
| `ether learn-stats` | Bandit arms |
| `ether version` | Package version |

Full list: [cli.md](cli.md)

## What this is not

- Not a cloud SaaS — runs on your machine.
- Not unbounded self-modification — promote is gated.
- Not a 70B coder — quality tracks local model class.

## License

MIT — see [LICENSE](../LICENSE).
