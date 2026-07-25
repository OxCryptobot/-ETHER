# @ETHER

**Local-first, self-extending, verified agentic coding system**

## Quick Start

```bash
git clone https://github.com/OxCryptobot/-ETHER.git
cd -ETHER
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

ether status
ether plan "add user authentication"
ether run "write a function that reverses a string"
ether run "write a fibonacci function" --json
ether audit path/to/file.py
pytest
```

**Requires**: Python 3.11+, Docker, Ollama (for local LLM + embeddings)

## Architecture

8 gems · typed Envelope protocol · exhaustive state machine · Docker sandbox as security boundary

| Gem | Role |
|-----|------|
| Clear Quartz | Sandbox execution |
| Rose Quartz | Local LLM routing |
| Citrine | Memory (Qdrant + embeddings) |
| Selenite | Planner |
| Amethyst | Interaction logging |
| Black Tourmaline | Security audit |
| Labradorite | Critique |
| Grandidierite | Controlled tool generation |

## Status

See [STATUS.md](STATUS.md) for live progress.

## License

MIT
