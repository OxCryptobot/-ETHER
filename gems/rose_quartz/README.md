# Rose Quartz

**Role**: Inference Router & MoE Classifier

## Behavior

- Prefers local models via Ollama
- Falls back to secondary local model on failure
- Cloud burst support planned (not yet implemented)
- Cost tracking planned

## Current Status

- Local Ollama routing: implemented
- Primary + fallback models: implemented
- Typed interface: ready
- Cloud burst: not yet
- Intelligent task classification: basic (will be improved)
