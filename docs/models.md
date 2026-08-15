# Local models (hardware-aware)

## Host lock (GTX 1650 4GB / 12GB RAM) — Turing SM 7.5

| Role | Model | Notes |
|------|-------|-------|
| Primary coder | `qwen3.5:4b-q4_K_M` | **Locked.** Ollama library `qwen3.5:4b` is already `file_type=Q4_K_M` (3.4GB). Explicit tag preferred. |
| Alias | `qwen3.5:4b` | Same quant; shorter tag |
| Fallback | `qwen2.5-coder:3b`, `phi3:mini` | Still ≤4B |
| Embeddings | `nomic-embed-text` | Citrine |

**Hard rule:** never auto-pull or select 7B+ on host profile (`core/model_select.py`).

### Q4_K_M tradeoffs (this card)

| Dimension | Reality on 4GB Turing |
|-----------|------------------------|
| VRAM weights | ~2.3–3.4 GB → fits with `num_ctx` ≤ 8192 |
| Quality vs FP16 | ~3–5% general drop; coding/reasoning more sensitive |
| vs Q5_K_M | Q5 needs ~3.5–4.5 GB → OOM or offload on 1650 |
| vs Q4_0 / Q4_K_S | Q4_K_M is the better K-quant (critical tensors higher bits) |
| Speed | Bandwidth-limited; quant helps, but **step count dominates latency** |

**Knee of the curve is Q4_K_M.** Below (Q3) hurts agent correctness. Above does not fit.

### Backend decisions (Phase 1)

| Backend | Verdict | Why |
|---------|---------|-----|
| **Ollama + GGUF Q4_K_M** | **Locked primary** | Works on Windows, fits 4GB, already in use |
| vLLM | Rejected | No official Windows; 4GB tight; FA2 needs SM≥8.0 |
| TensorRT-LLM | Rejected | Linux-first; modern support matrix starts Ampere+; complex build; 4GB impractical |

TensorRT (engine) / TensorRT-RTX can target SM 7.5 with limits (no FP8, limited INT8 WoQ). TensorRT-**LLM** is not a practical path for this host.

### Latency mitigations (host)

1. Keep model loaded (`keep_alive` high).
2. Cap `ETHER_NUM_CTX` ≤ 8192 (4096 for live).
3. FAST-first + live purge (foreman / host_agent).
4. Prefer tool_runtime / scripted until Phase 1D honest path is measured.
5. Single concurrent generation only.

Full analysis: `artifacts/performance_benchmark.json`.

## Cousin / high-VRAM only

| Role | Suggested | Notes |
|------|-----------|-------|
| Primary | 14B–32B coder Q4/Q5 | e.g. qwen2.5-coder:14b |
| Router | phi3:mini / gemma2:2b | optional |

Set `ETHER_HW_PROFILE=cousin` and explicit `ETHER_PRIMARY_MODEL`.

## Config

```
ETHER_PRIMARY_MODEL=qwen3.5:4b-q4_K_M
ETHER_EMBED_MODEL=nomic-embed-text
OLLAMA_BASE_URL=http://localhost:11434
ETHER_HW_PROFILE=host
# ETHER_NUM_CTX=8192
```
