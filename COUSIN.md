# @ETHER — Cousin velocity sheet

Two hardware profiles. **You (Linux / strong box / Qwen 3.6)** vs partner (Windows laptop).

---

## Your profile (Linux · strong GPU · Qwen 3.6 · no Docker)

| Item | Expected |
|------|----------|
| OS | Linux |
| LLM | **Qwen 3.6** via **Ollama** (Ollama may use a llama.cpp backend — fine) |
| Sandbox | **Local subprocess** — Docker **not** required |
| Role | Primary model quality, weekly scoreboard, hard tasks |

### Day-0 setup (~20–30 min)

```bash
git clone https://github.com/OxCryptobot/-ETHER.git
cd -ETHER
# if the folder name is awkward:
# mv -- -ETHER ETHER && cd ETHER

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Edit `.env`:

```env
OLLAMA_BASE_URL=http://localhost:11434

# MUST match `ollama list` exactly — Qwen 3.6 tag on your machine:
ETHER_PRIMARY_MODEL=qwen3:latest
# examples: qwen3:8b | qwen3:14b | qwen3:32b | whatever ollama list shows

ETHER_EMBED_MODEL=nomic-embed-text
ETHER_SANDBOX_TIMEOUT=120
ETHER_SANDBOX_RETRY=1

# No Docker:
ETHER_SANDBOX_BACKEND=local
ETHER_SANDBOX_PYTHON=python3

ETHER_LEARNING=1
ETHER_CURRICULUM=1
ETHER_EXPERIENCE=1
ETHER_RAG_BM25=1
ETHER_FLYWHEEL_PUSH=1
ETHER_FLYWHEEL_MIN_CONFIDENCE=0.7
```

Models:

```bash
ollama list
# pull only if missing — use YOUR Qwen 3.6 tag:
# ollama pull qwen3
ollama pull nomic-embed-text
```

Smoke:

```bash
source .venv/bin/activate
python scripts/smoke_test.py
pytest -q
python -m cli.main doctor
# expect sandbox_ok ✓ without Docker when BACKEND=local
python -m cli.main run "write a python function is_even(n) with assert is_even(4) and not is_even(5)"
```

### Daily

```bash
cd /path/to/ETHER
source .venv/bin/activate
export ETHER_GIT_RESET_OK=1
chmod +x scripts/start_daemon_linux.sh   # once
./scripts/start_daemon_linux.sh
# or single cycle:
# python scripts/run_smart_cycle.py
```

Dashboard: `python -m cli.main dashboard` → http://127.0.0.1:8787

### Weekly (you own quality numbers)

```bash
source .venv/bin/activate
python scripts/weekly_scoreboard.py
cat SCOREBOARD.md
python scripts/hidden_quiz.py --limit 10
python scripts/dataset_quiz.py --limit 8
```

### Notes for a powerful Linux box

- Prefer the **largest Qwen 3.6 quant you can run well** as `ETHER_PRIMARY_MODEL` — that is the advantage over the Windows 3B laptop.
- Ollama + llama.cpp backend is fine; @ETHER only needs the OpenAI-compatible Ollama HTTP API on `11434`.
- `ETHER_SANDBOX_BACKEND=local` is weaker isolation than Docker (trusted home use).
- Keep cloud burst **off** by default; use ablation only when measuring.
- Never commit `.env` or API keys.

### Break-glass

| Symptom | Fix |
|---------|-----|
| Model not found | `ollama list` → exact `ETHER_PRIMARY_MODEL` |
| Docker errors | `ETHER_SANDBOX_BACKEND=local` |
| MERGE_HEAD | `git merge --abort && git fetch && git reset --hard origin/main` |
| NOT HEALTHY | `python scripts/measurement_day.py` |
| Wrong Python | `source .venv/bin/activate` |

---

## Partner profile (Windows · lighter GPU · Docker)

| Item | Expected |
|------|----------|
| OS | Windows |
| LLM | e.g. `qwen2.5-coder:3b` |
| Sandbox | Docker (or `auto` fallback) |
| Role | Ops / daemon / Windows friction |

```powershell
cd C:\Users\Otcde\ETHER
$env:ETHER_GIT_RESET_OK = "1"
git fetch origin; git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q
```

---

## Split of labor

| Linux cousin | Windows partner |
|--------------|-----------------|
| Qwen 3.6 quality + hard tasks | Daemon / flywheel on laptop |
| Weekly scoreboard + hidden quizzes | Windows install issues |
| Optional burst ablation | Keys only in local `.env` |

## Do not

- Paste API keys in chat or commit `.env`
- Claim superiority without `SCOREBOARD.md`
- Assume Docker on the Linux profile
