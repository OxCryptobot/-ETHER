# Automated tool fabrication

```text
spec → implement (Rose Quartz | stub)
    → static safety
    → sandbox/compile self-test (Clear Quartz)
    → audit (Black Tourmaline)
    → pending_promote
    → optional auto-promote (ETHER_AUTO_PROMOTE=1)
```

## CLI

```powershell
# full LLM fabricate (needs ollama)
ether fabricate --name count_todos --purpose "Count TODO comments in a python file"

# stub only (no LLM)
ether fabricate --name count_todos --purpose "Count TODOs" --stub-only

# auto promote if all gates pass
ether fabricate --name count_todos --purpose "Count TODOs" --auto-promote

ether tool-list
ether tool-run repo_map --payload "{}"
ether quarantine
ether promote <quarantine_filename.py>
```

## Safety defaults
- New tools always land in `tools/quarantine/` first
- `ETHER_AUTO_PROMOTE=0` by default
- Network/eval/exec patterns fail static safety
- Log: `memory/tools/fabricate.jsonl`
