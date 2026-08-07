# ETHER sprint: phaseG_wire
# Restore tool_runtime, wire phaseG tools, pytest, optional hard scripted batch.
# Run via:  .\scripts\host_runner.ps1 -Sprint phaseg_wire -PushReport

# STEP: restore_tool_runtime
.\venv\Scripts\python.exe scripts\restore_tool_runtime.py

# STEP: wire_phaseg
.\venv\Scripts\python.exe scripts\wire_phaseg.py

# STEP: import_check
.\venv\Scripts\python.exe -c "from core.tool_runtime import TOOL_SPECS, ToolRuntime; names=sorted({t['name'] for t in TOOL_SPECS}); print('tools', names); assert 'apply_patch' in names and 'grep' in names; print('import OK')"

# STEP: pytest_tool_runtime
.\venv\Scripts\python.exe -m pytest tests\test_tool_runtime.py -q --tb=line

# STEP: scripted_hard_batch
.\venv\Scripts\python.exe -m scripts.batch_phase_d --arm direct --mode scripted --tier hard
