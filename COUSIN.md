# @ETHER — Cousin velocity sheet

Two hardware profiles. **You (Linux / strong box)** vs partner (Windows laptop).

---

## Your profile (Linux · strong GPU · Qwen 3.6 · no Docker)

| Item | Expected |
|------|----------|
| OS | Linux |
| LLM | **Qwen 3.6** via **Ollama** (or Ollama + llama.cpp backend) |
| Sandbox | **Local subprocess** — Docker **not** required |
| Role | Primary model quality, weekly scoreboard, hard tasks |

### Day-0 setup (~20–30 min)

```bash
# clone (private repo — use your GitHub access)
git clone https://github.com/OxCryptobot/-ETHER.git
cd -ETHER   # if folder is awkward: mv -- -ETHER ETHER && cd ETHER

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
```

Edit `.env` for **your** machine:

```env
OLLAMA_BASE_URL=http://localhost:11434

# Use the exact tag from: ollama list
# Examples (pick what you actually pulled for Qwen 3.6):
ETHER_PRIMARY_MODEL=qwen3:latest
# or e.g. qwen3:8b / qwen3:14b / qwen3:32b — whatever ollama list shows

ETHER_EMBED_MODEL=nomic-embed-text
ETHER_SANDBOX_TIMEOUT=120
ETHER_SANDBOX_RETRY=1

# No Docker on this box:
ETHER_SANDBOX_BACKEND=local
# optional: ETHER_SANDBOX_PYTHON=python3

ETHER_LEARNING=1
ETHER_CURRICULUM=1
ETHER_EXPERIENCE=1
ETHER_RAG_BM25=1
ETHER_FLYWHEEL_PUSH=1
ETHER_FLYWHEEL_MIN_CONFIDENCE=0.7
```

Pull models (names must match `ollama list`):

```bash
ollama list
# If Qwen 3.6 is not present yet, pull the tag you use, e.g.:
# ollama pull qwen3
# ollama pull qwen3:14b
ollama pull nomic-embed-text   # embeddings for optional paths
```

Smoke:

```bash
source .venv/bin/activate
python scripts/smoke_test.py
pytest -q
python -m cli.main doctor
python -m cli.main run "write a python function is_even(n) with assert is_even(4) and not is_even(5)"
```

You should see sandbox success **without** Docker when `ETHER_SANDBOX_BACKEND=local`.

### Daily (one terminal)

```bash
cd /path/to/ETHER
source .venv/bin/activate
export ETHER_GIT_RESET_OK=1
# optional daemon if scripts/start_daemon exists; else:
python scripts/run_smart_cycle.py
# or loop:
# while true; do python scripts/run_smart_cycle.py; sleep 900; done
```

Dashboard (if installed):

```bash
python -m cli.main dashboard
# http://127.0.0.1:8787
```

### Weekly scoreboard (you own this — stronger box)

```bash
source .venv/bin/activate
python scripts/weekly_scoreboard.py
cat SCOREBOARD.md
# optional hidden/dataset pressure tests:
python scripts/hidden_quiz.py --limit 10
python scripts/dataset_quiz.py --limit 8
```

### Notes for a powerful Linux box

- Prefer a **larger Qwen 3.6 quant** as `ETHER_PRIMARY_MODEL` — that is your main advantage over the Windows 3B laptop.
- Keep **burst off** by default on your box unless comparing; local should win on quality.
- `ETHER_SANDBOX_BACKEND=local` is **weaker isolation** than Docker (trusted home use). Do not feed untrusted network code into the sandbox.
- Never commit `.env` or API keys.

### When something breaks

| Symptom | Fix |
|---------|-----|
| Model not found | `ollama list` → set exact `ETHER_PRIMARY_MODEL` |
| Sandbox / Docker errors | Confirm `ETHER_SANDBOX_BACKEND=local` in `.env` |
| MERGE_HEAD | `git merge --abort` then `git fetch && git reset --hard origin/main` |
| NOT HEALTHY | `python scripts/measurement_day.py` or `weekly_scoreboard.py` |
| Wrong Python | always `source .venv/bin/activate` |

---

## Partner profile (Windows · lighter GPU · Docker)

| Item | Expected |
|------|----------|
| OS | Windows |
| LLM | Smaller coder (e.g. `qwen2.5-coder:3b`) |
| Sandbox | Docker `python:3.12-slim` |
| Role | Ops, daemon, Windows friction |

```powershell
cd C:\Users\Otcde\ETHER
$env:ETHER_GIT_RESET_OK = "1"
git fetch origin; git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q
# .env: ETHER_PRIMARY_MODEL=qwen2.5-coder:3b, ETHER_SANDBOX_BACKEND=docker (default)
```

---

## Split of labor

| Linux cousin (you) | Windows partner |
|--------------------|-----------------|
| Qwen 3.6 quality runs | Daemon / flywheel on laptop |
| Weekly scoreboard + hidden quizzes | Windows install friction |
| Hard / multifile curriculum pressure | Report FAIL gates |
| Optional burst experiments | Keep keys local only |

## Do not

- Paste API keys in chat or commit `.env`
- Claim “beats Cursor” without `SCOREBOARD.md` numbers
- Mix Docker assumptions into the Linux `.env` if you set `local`
