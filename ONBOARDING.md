# @ETHER — Onboarding (Linux cousin + Windows partner)

Local-first **verified** coding agent: plan → code (Ollama) → sandbox → audit → gate → learn.

Not a claim that it beats Cursor/Claude Code. Trust **SCOREBOARD.md** only.

---

## Profile A — Linux · strong machine · Qwen 3.6 · **no Docker**

### Prerequisites

- Linux
- Python 3.11+
- **Ollama** with **Qwen 3.6** already working (`ollama list`)
- Git
- **Docker not required** when using local sandbox

### Setup

```bash
git clone https://github.com/OxCryptobot/-ETHER.git
cd -ETHER   # or rename folder to ETHER

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

### `.env` (Linux / Qwen 3.6)

```env
OLLAMA_BASE_URL=http://localhost:11434

# MUST match `ollama list` exactly — examples only:
ETHER_PRIMARY_MODEL=qwen3:latest
# ETHER_PRIMARY_MODEL=qwen3:14b
# ETHER_PRIMARY_MODEL=qwen3:32b

ETHER_EMBED_MODEL=nomic-embed-text
ETHER_SANDBOX_TIMEOUT=120
ETHER_SANDBOX_RETRY=1

# Critical for no-Docker boxes:
ETHER_SANDBOX_BACKEND=local
ETHER_SANDBOX_PYTHON=python3

ETHER_LEARNING=1
ETHER_CURRICULUM=1
ETHER_EXPERIENCE=1
ETHER_RAG_BM25=1
ETHER_FLYWHEEL_PUSH=1
ETHER_FLYWHEEL_MIN_CONFIDENCE=0.7
```

Confirm model:

```bash
ollama list
ollama run <your-qwen3.6-tag> "write a one-line python is_even"
```

### Verify

```bash
source .venv/bin/activate
python scripts/smoke_test.py
pytest -q
python -m cli.main doctor
python -m cli.main run "write a python function is_even(n) with assert is_even(4) and not is_even(5)"
```

### Autonomy / quality (your box is the muscle)

```bash
export ETHER_GIT_RESET_OK=1
python scripts/run_smart_cycle.py
python scripts/weekly_scoreboard.py
cat SCOREBOARD.md
```

### Security note (local sandbox)

`ETHER_SANDBOX_BACKEND=local` runs code with host `python3` under a timeout. Isolation is **weaker** than Docker. Use only for trusted objectives on your machine.

---

## Profile B — Windows · lighter GPU · Docker

### Prerequisites

- Windows 10/11
- Python 3.11+
- Ollama
- **Docker Desktop** (default sandbox)
- Git

### Setup

```powershell
git clone https://github.com/OxCryptobot/-ETHER.git
cd -ETHER
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
```

### `.env` (Windows laptop)

```env
ETHER_PRIMARY_MODEL=qwen2.5-coder:3b
ETHER_EMBED_MODEL=nomic-embed-text
ETHER_SANDBOX_BACKEND=docker
ETHER_SANDBOX_TIMEOUT=120
```

```powershell
ollama pull qwen2.5-coder:3b
docker pull python:3.12-slim
python scripts\smoke_test.py
pytest -q
python -m cli.main run "write a python function is_even(n) with assert is_even(4)"
```

### One-window autonomy

```powershell
$env:ETHER_GIT_RESET_OK = "1"
powershell -ExecutionPolicy Bypass -File .\scripts\start_daemon.ps1 -Foreground
```

Dashboard: http://127.0.0.1:8787

---

## Optional cloud burst (either profile)

Keys **only** in local `.env` — never commit or paste in chat:

```env
ETHER_BURST=1
ETHER_BURST_URL=https://api.groq.com/openai/v1
ETHER_BURST_MODEL=llama-3.3-70b-versatile
ETHER_BURST_API_KEY=...
ETHER_BURST_ON_FAIL=1
```

On the Linux/Qwen box, prefer **local-first**; use burst mainly for ablation science (`scripts/burst_ablation.py`).

---

## Golden rules

1. Use the project **venv** (`source .venv/bin/activate` or Windows Activate.ps1).
2. `ETHER_PRIMARY_MODEL` must match `ollama list` **exactly**.
3. Linux no-Docker → `ETHER_SANDBOX_BACKEND=local`.
4. Windows default → Docker sandbox.
5. Trust `SCOREBOARD.md`, not adjectives.
6. Quarantine tools are untrusted until reconcile/promote.

Full partner checklist: **[COUSIN.md](./COUSIN.md)**.
