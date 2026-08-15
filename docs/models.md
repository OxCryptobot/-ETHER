# Local models (hardware-aware)

## Host lock (GTX 1650 4GB / 12GB RAM)

| Role | Model | Notes |
|------|-------|-------|
| Primary coder | `qwen3.5:4b` (Q4 class) | **Only** class allowed on host. Prefer explicit Q4_K_M / Q4_0 if tagged. |
| Fallback | `qwen2.5-coder:3b`, `phi3:mini` | Still ≤4B |
| Embeddings | `nomic-embed-text` | Citrine |

**Hard rule:** never auto-pull or select 7B+ on host profile (`core/model_select.py`).

### Quantization (must-read for this card)

- **Q4_K_M / Q4_0**: only practical choice. Weights ~2.3–3.3 GB + KV. Fits with `num_ctx` ≤ 8192.
- **Q5+ / Q8 / FP16**: will OOM or force CPU offload → latency collapses.
- Quality trade-off on Q4 is real (~3–5% general, more on hard coding/reasoning) but unavoidable on 4 GB.
- Verify with `ollama show qwen3.5:4b` and `nvidia-smi` under load.

### Latency mitigations (host)

1. Keep model loaded (`keep_alive` high).
2. Cap `ETHER_NUM_CTX` / `num_ctx` ≤ 8192 (4096 for live experiments).
3. FAST-first policy + live purge (already in foreman / host_agent).
4. Prefer tool_runtime / scripted over open live agent loops until Phase 1D honest path is measured.
5. Single concurrent generation only.

Full analysis + vLLM investigation: `artifacts/performance_benchmark.json` (quantization_impact, vllm_investigation, latency_mitigation_steps).

## Cousin / high-VRAM only

| Role | Suggested | Notes |
|------|-----------|-------|
| Primary | 14B–32B coder Q4/Q5 | e.g. qwen2.5-coder:14b, 32b-q4_k_m |
| Router | phi3:mini / gemma2:2b | optional |

Set `ETHER_HW_PROFILE=cousin` and explicit `ETHER_PRIMARY_MODEL`.

## Config

```
ETHER_PRIMARY_MODEL=qwen3.5:4b
ETHER_EMBED_MODEL=nomic-embed-text
OLLAMA_BASE_URL=http://localhost:11434
ETHER_HW_PROFILE=host          # default
# ETHER_NUM_CTX=8192           # recommended host default
```
