# Changelog

## v0.1.1 — unreleased

### Added
- `ether doctor --json`, `ether ping`, `ether env`, `ether which`
- `ether clean-runs`, `ether quarantine`, `ether tools`, `ether promote`
- Optional LLM-assisted planning via `ETHER_LLM_PLAN=1`
- Stage timings (`duration_ms`) in pipeline results
- Docs: threat model, gems index, examples, FAQ, CLI list, Windows setup, v0.2 roadmap
- Makefile, editorconfig, pre-commit sample, SECURITY.md

### Improved
- Pipeline stage tracking + run persistence
- Manifest validation
- Grandidierite name sanitization
- Rose Quartz model-not-found / Ollama connection errors
- Registry missing-gem error messages

## v0.1.0 — 2026-07-25

### Added
- 8-gem architecture with typed Envelope protocol
- Orchestrator state machine with retries and loop guards
- End-to-end pipeline: plan → code → sandbox → audit
- CLI core commands
- Basic implementations for all gems
- Unit + smoke tests
- STATUS.md live tracker
