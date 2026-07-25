# @ETHER

Local-first, self-extending, verified agentic coding system.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Requires **Docker** + **Ollama** for the full pipeline. See [docs/models.md](docs/models.md) and [docs/setup-windows.md](docs/setup-windows.md).

## Usage

```bash
ether doctor
ether plan "add auth"
ether run "write a function that reverses a string"
ether run "..." --json --critique
ether audit path/to/file.py
ether index ./src
ether search "authentication"
ether runs
ether env
ether which
pytest
python scripts/smoke_test.py
```

## Docs

- [STATUS.md](STATUS.md) — live progress
- [Architecture](docs/architecture.md)
- [Threat model](docs/threat-model.md)
- [Security policy](SECURITY.md)
- [v0.2 roadmap](docs/v0.2-roadmap.md)
- [Contributing](CONTRIBUTING.md)

## License

MIT
