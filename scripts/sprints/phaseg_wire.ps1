# ETHER sprint: phaseg_wire
# MUST use $env:ETHER_PY (set by host_runner).

# STEP: restore_tool_runtime
& $env:ETHER_PY scripts\restore_tool_runtime.py

# STEP: wire_phaseg
& $env:ETHER_PY scripts\wire_phaseg.py

# STEP: import_check
& $env:ETHER_PY -c "from core.tool_runtime import TOOL_SPECS; names=sorted({t['name'] for t in TOOL_SPECS}); print('tools', names); assert 'apply_patch' in names and 'grep' in names; print('import OK')"

# STEP: pytest_tool_runtime
& $env:ETHER_PY -m pytest tests\test_tool_runtime.py -q --tb=line

# STEP: scripted_hard_batch
& $env:ETHER_PY -m scripts.batch_phase_d --arm direct --mode scripted --tier hard
