# Changelog

## v0.2.0 — 2026-07-31

Market package. Stages 0–4 closed on reference host (GTX 1650 4GB / 12GB / Qwen 3.5 4B).

### Added
- Ranked `repo_map` by objective; multi-file `# file:` sandbox cycle
- Infinity topology: Labradorite critique mandatory on product path + fabricate
- Citrine/Qdrant health in `ether doctor`; pattern index on pass + promote
- Controlled evolution metrics: fail_streak, quarantine_tools, persistent_tools
- `ETHER_FORCE_STRATEGY` for deterministic arm tests
- `docs/QUICKSTART.md` third-party runbook
- `core/__version__.py` single version source (`0.2.0`)

### Improved
- `run_tool` flattens result keys (repo_map visible to pipeline)
- Fabricate auto-promote runs the same promotion gate as reconcile
- PowerShell UTF-8 BOM accepted on `--payload-file`
- Host hardware profile: no 7B/14B auto-pull on 4GB VRAM

### Safe defaults (unchanged product rules)
- `ETHER_AUTO_PROMOTE=0`
- `ETHER_AUTO_FABRICATE_ON_FAIL=0`
- No auto push to origin

## v0.1.1 — unreleased (folded into 0.2.0)

### Added
- `ether doctor --json`, `ether ping`, `ether env`, `ether which`
- `ether clean-runs`, `ether quarantine`, `ether tools`, `ether promote`
- Optional LLM-assisted planning via `ETHER_LLM_PLAN=1`
- Stage timings (`duration_ms`) in pipeline results

## v0.1.0 — 2026-07-25

### Added
- 8-gem architecture with typed Envelope protocol
- Orchestrator state machine with retries and loop guards
- End-to-end pipeline: plan → code → sandbox → audit
- CLI core commands
- Unit + smoke tests
