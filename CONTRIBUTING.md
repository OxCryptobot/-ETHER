# Contributing to @ETHER

## Setup

```bash
git clone https://github.com/OxCryptobot/-ETHER.git
cd -ETHER
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

## Tests

```bash
python scripts/smoke_test.py   # no Docker/Ollama required
pytest                         # unit + mocked integration
make test
```

## Branch workflow

```bash
git checkout -b feature/my-change
# edit
git add -A && git commit -m "feat: ..."
git push -u origin feature/my-change
```

Open a PR against `main`.

## Architecture rules

- Gem I/O via `Envelope` / `ResponseEnvelope`
- No untyped `Dict[str, Any]` as primary contracts
- Sandbox is the real security boundary
- Update `STATUS.md` for meaningful progress
