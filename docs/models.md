# Suggested local models

| Role | Suggested model | Notes |
|------|-----------------|-------|
| Primary coder | `qwen3-coder-next:32b-q4_k_m` or similar 14B–32B coder | Best quality if VRAM allows |
| Fallback coder | `deepseek-r1:8b` / `qwen2.5-coder:7b` | Faster, lower VRAM |
| Embeddings | `nomic-embed-text` | Used by Citrine |
| Optional router | `phi3:mini` / `gemma2:2b` | Future intelligent routing |

Pull examples:
```bash
ollama pull nomic-embed-text
ollama pull deepseek-r1:8b
```

Configure via `.env`:
```
ETHER_PRIMARY_MODEL=...
ETHER_EMBED_MODEL=nomic-embed-text
OLLAMA_BASE_URL=http://localhost:11434
ETHER_LLM_PLAN=0   # set to 1 for LLM-assisted Selenite plans
```
