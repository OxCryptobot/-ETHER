# @ETHER — Cousin velocity sheet

> **Read `docs/FINDINGS.md` first.** Three days of measurement (2026-07-29)
> found that ETHER does **not** beat a bare model — 0.292 vs 0.317 on a 3B,
> 0.874 vs 0.933 on a 35B — and that seven separate channels had been leaking
> the answers into the prompt. Every score predating that is void.
>
> **Sandbox:** prefer `docker` wherever Docker exists. `local` runs
> model-authored code on the host with no isolation; the old advice here
> assumed no Docker was available.
>
> **After cloning:** `memory/` is gitignored, so benchmark datasets do not
> transfer. Run `python scripts/build_headroom.py` and
> `python scripts/build_calibrated.py`.

Two profiles: **you (Linux / strong / Qwen 3.6)** vs Windows partner.

---

## Your profile (Linux · Qwen 3.6 · no Docker)

| Item | Expected |
|------|----------|
| OS | Linux |
| LLM | **Qwen 3.6** via **Ollama** (llama.cpp backend OK) |
| Sandbox | `ETHER_SANDBOX_BACKEND=docker` (see note) |
| Role | Quality model, weekly scoreboard, hard tasks |

### Day-0

```bash
git clone https://github.com/OxCryptobot/-ETHER.git
cd -ETHER
# mv -- -ETHER ETHER && cd ETHER   # optional rename

bash scripts/linux_bootstrap.sh
# or manual: python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
```

`.env` essentials:

```env
OLLAMA_BASE_URL=http://localhost:11434

# Exact tag from `ollama list`. Qwen 3.6 examples on Ollama:
#   qwen3.6:27b
#   qwen3.6:35b
#   or community coder tags you already pulled
ETHER_PRIMARY_MODEL=qwen3.6:27b

ETHER_EMBED_MODEL=nomic-embed-text
ETHER_SANDBOX_BACKEND=local
ETHER_SANDBOX_PYTHON=python3
ETHER_SANDBOX_TIMEOUT=120

ETHER_LEARNING=1
ETHER_CURRICULUM=1
ETHER_EXPERIENCE=1
ETHER_RAG_BM25=1
ETHER_FLYWHEEL_PUSH=1
ETHER_FLYWHEEL_MIN_CONFIDENCE=0.7
```

```bash
ollama list
# ollama pull qwen3.6:27b   # only if missing
ollama pull nomic-embed-text

source .venv/bin/activate
python -m cli.main doctor
python -m cli.main run "write a python function is_even(n) with assert is_even(4) and not is_even(5)"
```

### Daily

```bash
source .venv/bin/activate
export ETHER_GIT_RESET_OK=1
./scripts/start_daemon_linux.sh
# optional user service:
# mkdir -p ~/.config/systemd/user && cp deploy/ether.service ~/.config/systemd/user/
# systemctl --user daemon-reload && systemctl --user enable --now ether
```

### Weekly (you own numbers)

```bash
python scripts/weekly_scoreboard.py
cat SCOREBOARD.md
```

### Notes

- Larger Qwen 3.6 quant = your advantage vs Windows 3B.
- Local sandbox = weaker isolation than Docker (trusted use).
- Burst off by default; ablation only for science.
- Never commit `.env`.

### Break-glass

| Symptom | Fix |
|---------|-----|
| Model not found | exact `ollama list` tag |
| Docker noise | `ETHER_SANDBOX_BACKEND=local` |
| MERGE_HEAD | `git merge --abort && git fetch && git reset --hard origin/main` |
| NOT HEALTHY | `python scripts/measurement_day.py` |

---

## Partner (Windows · lighter · Docker/auto)

```powershell
cd C:\Users\Otcde\ETHER
$env:ETHER_GIT_RESET_OK = "1"
git fetch origin; git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q
.\.venv\Scripts\python.exe -m cli.main doctor
```

## Split

| Linux cousin | Windows partner |
|--------------|-----------------|
| Qwen 3.6 quality + hard quizzes | Daemon / Windows ops |
| Weekly SCOREBOARD | Flywheel reports |
