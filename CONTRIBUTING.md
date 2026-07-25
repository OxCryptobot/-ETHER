# Contributing to @ETHER

## For collaborators (including Queensone)

1. Accept the GitHub invite to the private repo
2. Clone and setup:

```bash
git clone https://github.com/OxCryptobot/-ETHER.git
cd -ETHER
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

3. Run smoke test (no Docker/Ollama needed):

```bash
python scripts/smoke_test.py
pytest
```

4. Branch workflow:

```bash
git checkout -b feature/my-change
# ... edit ...
git add -A && git commit -m "feat: ..."
git push -u origin feature/my-change
```

5. Open a PR against `main`.

## Architecture rules

- All gem I/O goes through `Envelope` / `ResponseEnvelope`
- No `Dict[str, Any]` as primary gem contracts
- Sandbox is the real security boundary
- Update `STATUS.md` when you complete a meaningful chunk of work
