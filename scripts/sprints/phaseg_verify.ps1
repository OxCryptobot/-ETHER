# ETHER sprint: phaseg_verify
# MUST use $env:ETHER_PY (set by host_runner). Relative venv paths are FORBIDDEN.

# STEP: ensure_wired
& $env:ETHER_PY scripts\restore_tool_runtime.py
& $env:ETHER_PY scripts\wire_phaseg.py

# STEP: import_check
& $env:ETHER_PY -c "from core.tool_runtime import TOOL_SPECS; names=sorted({t['name'] for t in TOOL_SPECS}); print('tools', names); assert 'apply_patch' in names and 'grep' in names; print('import OK')"

# STEP: pytest_tool_runtime
& $env:ETHER_PY -m pytest tests\test_tool_runtime.py -q --tb=line

# STEP: scripted_hard_batch
& $env:ETHER_PY -m scripts.batch_phase_d --arm direct --mode scripted --tier hard

# STEP: commit_runtime_if_dirty
git add core/tool_runtime.py
git diff --cached --quiet; if ($LASTEXITCODE -ne 0) { git commit -m "phaseG: commit wired tool_runtime from host"; git push origin main }
