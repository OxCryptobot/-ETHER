# Windows setup

Reference host: **GTX 1650 4GB VRAM · 12GB RAM · x64**. Stay on ≤4B models.

```powershell
git clone https://github.com/OxCryptobot/-ETHER.git
cd -ETHER
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env

# Models (exact tags from `ollama list`)
ollama pull qwen3.5:4b
ollama pull nomic-embed-text

# Optional but recommended — Citrine memory
docker compose -f deploy/docker-compose.qdrant.yml up -d

ether doctor
ether run "write is_even(n) with asserts"
```

If `ETHER_PRIMARY_MODEL` does not match `ollama list`, edit `.env`.

Without Docker: set `ETHER_SANDBOX_BACKEND=local` in `.env` (weaker isolation).

See [QUICKSTART.md](QUICKSTART.md) for multi-file and evolution commands.
