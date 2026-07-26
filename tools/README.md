# @ETHER Tools (Grandidierite)

## Design rules
1. One job per tool
2. JSON in / JSON out
3. No network by default
4. Quarantine first → promote
5. Callable via Grandidierite registry

## Layout
- `tools/persistent/` — promoted, trusted tools (this catalog)
- `tools/quarantine/` — newly generated, not trusted yet
- `tools/_lib.py` — shared JSON I/O helpers

## Run a tool
```powershell
python tools/persistent/secret_scan.py '{"text": "password = \"supersecretvalue\""}'
python tools/persistent/repo_map.py '{}'
python tools/persistent/bandit_report.py '{}'
```

## Via gem registry
```python
from gems.grandidierite.registry import list_tools, run_tool
print(list_tools())
print(run_tool("repo_map", {}))
```

## Catalog (persistent)
See filenames under `tools/persistent/` — verification, memory, git, security, learning, env probes, prompt helpers, meta tools.
