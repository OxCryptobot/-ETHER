# @ETHER

Local-first, self-extending, verified agentic coding system.

<!-- badges: add CI badges when public workflows exist -->

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Requires **Docker** + **Ollama** for the full pipeline. See [docs/models.md](docs/models.md) and [docs/setup-windows.md](docs/setup-windows.md).

Optional LLM-assisted plans:
```bash
export ETHER_LLM_PLAN=1
ether plan "implement caching layer"
```

## Usage

```bash
ether doctor
ether ping
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

Full command list: [docs/cli.md](docs/cli.md)

## Docs

- [STATUS.md](STATUS.md)
- [Architecture](docs/architecture.md)
- [Threat model](docs/threat-model.md)
- [Security policy](SECURITY.md)
- [FAQ](docs/faq.md)
- [v0.2 roadmap](docs/v0.2-roadmap.md)
- [Contributing](CONTRIBUTING.md)
- [Release checklist 0.1.1](docs/release-checklist-0.1.1.md)

## License

MIT
