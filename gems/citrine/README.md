# Citrine

**Role:** Modular memory & retrieval gem (Qdrant + Ollama embeddings).

Citrine is a **first-class** gem in Stage 2 Modular Intelligence — not an optional side effect of the pipeline.

## Collections

| Collection | Purpose |
|------------|---------|
| `ether_code` | Chunked source / repo knowledge |
| `patterns` | **Verified-only** pass artifacts (sandbox exit 0) |
| `failures` | Structured failure lessons (no full cheatsheets) |
| `runs` | Run continuity summaries |

## Rules

1. **Zero-vector ban** — failed embeds raise; never store `[0.0]*768`
2. **Verified writes** — callers must only insert sandbox-passed code into `patterns`
3. **Leak-safe retrieve** — pipeline filters hits that would show the solution under test (prompt_guard)
4. **Honest health** — `Citrine.health()` / doctor report reachability + embed_ok

## Host setup

```powershell
docker compose -f deploy/docker-compose.qdrant.yml up -d
ollama pull nomic-embed-text
# QDRANT_URL=http://localhost:6333 in .env
```

## API

Envelope actions: `search`, `add`, `health` via `CitrineRequest`.
