# @ETHER

**Local-first super-agentic coding system** — modular intelligence, verified execution, controlled evolution.

Every code artifact is sandboxed and scored **before** you see it. Tools the system invents stay quarantined until a promotion gate clears them. Memory compounds via Citrine/Qdrant when available.

| Pillar | What it means |
|--------|----------------|
| **Modular Intelligence** | 8 typed gems (plan, code, sandbox, audit, critique, memory, evolve, tools) |
| **Verified Execution** | Clear Quartz sandbox + asserts + audit before delivery |
| **Controlled Evolution** | Grandidierite fabricate → quarantine → gated promote |

**Version:** 0.2.0 · **Python:** ≥3.11 · **License:** MIT

## Requirements

- Ollama + a ≤4B coder model (default `qwen3.5:4b` for GTX 1650 / 12GB hosts)
- Docker recommended (sandbox + Qdrant); local backend works with weaker isolation

## Install (60 seconds)

```bash
git clone https://github.com/OxCryptobot/-ETHER.git && cd -ETHER
python -m venv .venv && source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
cp .env.example .env                                  # Windows: copy .env.example .env
ether doctor
```

Full third-party path (Windows, Qdrant, multi-file): **[docs/QUICKSTART.md](docs/QUICKSTART.md)**

## Usage

```bash
ether doctor
ether run "write is_even(n) with asserts"
ether run "in this repo, summarize public functions in core/patterns.py as a dict; include asserts"
ether fabricate --name probe --purpose "demo" --stub-only
ether learn-stats
```

## Safe by default

- `ETHER_AUTO_PROMOTE=0` — no silent tool promotion
- `ETHER_AUTO_FABRICATE_ON_FAIL=0` — no silent self-extension
- Host profile caps models at 4B unless you opt into `cousin`

## Docs

- [Quickstart](docs/QUICKSTART.md) · [Windows setup](docs/setup-windows.md) · [CLI](docs/cli.md)
- [Architecture](docs/architecture.md) · [Threat model](docs/threat-model.md) · [SECURITY](SECURITY.md)
- [STATUS](STATUS.md) · [CHANGELOG](CHANGELOG.md)

## License

MIT
