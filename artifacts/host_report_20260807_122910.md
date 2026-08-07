# Host report - 20260807_122910

| field | value |
|---|---|
| sprint | phaseg_wire |
| python | C:\Users\Otcde\ETHER\.venv\Scripts\python.exe |
| host | DESKTOP-HUKTQDQ |
| passed | 4/5 |
| failed | 1 |

## STEP 2: restore_tool_runtime - PASS (exit=0, 0.73s)

```powershell
.\.venv\Scripts\python.exe scripts\restore_tool_runtime.py
```

```
restored tool_runtime.py 18515 bytes
```

## STEP 3: wire_phaseg - PASS (exit=0, 0.111s)

```powershell
.\.venv\Scripts\python.exe scripts\wire_phaseg.py
```

```
wired phaseG 20900
syntax OK
```

## STEP 4: import_check - PASS (exit=0, 0.824s)

```powershell
.\.venv\Scripts\python.exe -c "from core.tool_runtime import TOOL_SPECS; names=sorted({t['name'] for t in TOOL_SPECS}); print('tools', names); assert 'apply_patch' in names and 'grep' in names; print('import OK')"
```

```
tools ['apply_patch', 'done', 'glob', 'grep', 'list_files', 'read_file', 'rollback', 'run_tests', 'write_file']
import OK
```

## STEP 5: pytest_tool_runtime - FAIL (exit=1, 4.083s)

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_tool_runtime.py -q --tb=line
```

```
.....FFFFFFFF..F                                                         [100%]
================================== FAILURES ===================================
E   TypeError: ToolRuntime.__init__() got an unexpected keyword argument 'run_ruff'
C:\Users\Otcde\ETHER\tests\test_tool_runtime.py:83: TypeError: ToolRuntime.__init__() got an unexpected keyword argument 'run_ruff'
E   TypeError: ToolRuntime.__init__() got an unexpected keyword argument 'run_ruff'
C:\Users\Otcde\ETHER\tests\test_tool_runtime.py:106: TypeError: ToolRuntime.__init__() got an unexpected keyword argument 'run_ruff'
E   TypeError: ToolRuntime.__init__() got an unexpected keyword argument 'run_ruff'
C:\Users\Otcde\ETHER\tests\test_tool_runtime.py:125: TypeError: ToolRuntime.__init__() got an unexpected keyword argument 'run_ruff'
E   TypeError: ToolRuntime.__init__() got an unexpected keyword argument 'run_ruff'
C:\Users\Otcde\ETHER\tests\test_tool_runtime.py:150: TypeError: ToolRuntime.__init__() got an unexpected keyword argument 'run_ruff'
E   TypeError: ToolRuntime.__init__() got an unexpected keyword argument 'run_ruff'
C:\Users\Otcde\ETHER\tests\test_tool_runtime.py:164: TypeError: ToolRuntime.__init__() got an unexpected keyword argument 'run_ruff'
E   TypeError: ToolRuntime.__init__() got an unexpected keyword argument 'run_ruff'
C:\Users\Otcde\ETHER\tests\test_tool_runtime.py:177: TypeError: ToolRuntime.__init__() got an unexpected keyword argument 'run_ruff'
E   TypeError: ToolRuntime.__init__() got an unexpected keyword argument 'run_ruff'
C:\Users\Otcde\ETHER\tests\test_tool_runtime.py:190: TypeError: ToolRuntime.__init__() got an unexpected keyword argument 'run_ruff'
E   TypeError: ToolRuntime.__init__() got an unexpected keyword argument 'run_ruff'
C:\Users\Otcde\ETHER\tests\test_tool_runtime.py:201: TypeError: ToolRuntime.__init__() got an unexpected keyword argument 'run_ruff'
E   TypeError: ToolRuntime.__init__() got an unexpected keyword argument 'run_ruff'
C:\Users\Otcde\ETHER\tests\test_tool_runtime.py:252: TypeError: ToolRuntime.__init__() got an unexpected keyword argument 'run_ruff'
=========================== short test summary info ===========================
FAILED tests/test_tool_runtime.py::test_scripted_fix_greeter - TypeError: Too...
FAILED tests/test_tool_runtime.py::test_scripted_fix_wallet - TypeError: Tool...
FAILED tests/test_tool_runtime.py::test_apply_patch_fail_closed_no_match - Ty...
FAILED tests/test_tool_runtime.py::test_rollback_restores_prior_content - Typ...
FAILED tests/test_tool_runtime.py::test_grep_finds_symbol - TypeError: ToolRu...
FAILED tests/test_tool_runtime.py::test_glob_py_files - TypeError: ToolRuntim...
FAILED tests/test_tool_runtime.py::test_path_escape_refused - TypeError: Tool...
FAILED tests/test_tool_runtime.py::test_max_steps_without_fix - TypeError: To...
FAILED tests/test_tool_runtime.py::test_llm_decide_fn_scripted_fix_greeter - ...
```

## STEP 6: scripted_hard_batch - PASS (exit=0, 3.085s)

```powershell
.\.venv\Scripts\python.exe -m scripts.batch_phase_d --arm direct --mode scripted --tier hard
```

```
config: model=qwen3.5:4b max_steps=12 timeout=400.0

=== arm=direct mode=scripted fixtures=['lru', 'merge', 'ledger', 'topo', 'intervals'] ===
[PASS] merge      arm=direct score=1.0 steps=4 elapsed=1.507s
[PASS] topo       arm=direct score=1.0 steps=4 elapsed=1.52s
[PASS] ledger     arm=direct score=1.0 steps=6 elapsed=1.51s
[PASS] lru        arm=direct score=1.0 steps=4 elapsed=1.531s
[PASS] intervals  arm=direct score=1.0 steps=4 elapsed=1.177s

=== summary matrix ===
fixture    direct     pipeline   bare      
lru        PASS       --         --        
merge      PASS       --         --        
ledger     PASS       --         --        
topo       PASS       --         --        
intervals  PASS       --         --        

summary: 5/5 passed
scoreboard: artifacts\scoreboard_phase_d.json
```

