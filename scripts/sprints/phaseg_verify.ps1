# ETHER sprint: phaseg_verify
# Run:  .\scripts\host_runner.ps1 -Sprint phaseg_verify -PushReport

# STEP: ensure_wired
.\.venv\Scripts\python.exe scripts\restore_tool_runtime.py
.\.venv\Scripts\python.exe scripts\wire_phaseg.py

# STEP: import_check
.\.venv\Scripts\python.exe -c "from core.tool_runtime import TOOL_SPECS; names=sorted({t['name'] for t in TOOL_SPECS}); print('tools', names); assert 'apply_patch' in names and 'grep' in names; print('import OK')"

# STEP: pytest_tool_runtime
.\.venv\Scripts\python.exe -m pytest tests\test_tool_runtime.py -q --tb=line

# STEP: scripted_hard_batch
.\.venv\Scripts\python.exe -m scripts.batch_phase_d --arm direct --mode scripted --tier hard

# STEP: commit_runtime_if_dirty
git add core/tool_runtime.py
git diff --cached --quiet; if ($LASTEXITCODE -ne 0) { git commit -m "phaseG: commit wired tool_runtime from host"; git push origin main }
