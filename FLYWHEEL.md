# @ETHER Flywheel (autonomous)

> Last cycle: **2026-07-26T03:13:00.656409+00:00**  
> Result: **FAIL — audit report filed**  
> Confidence: **0.000** (min 0.7) · Audit: **False**  
> Pull: **OK**  * branch            main       -> FETCH_HEAD  
> Report pushed: **False** · Model: `qwen2.5-coder:3b`  
> Reason: `static_gates_failed`

## Policy
- Git: fetch + ff-only; ETHER_GIT_RESET_OK=1 allows hard reset
- ETHER_PULL_SOFT=1 (default): network/pull issues soft-continue
- PASS/FAIL reports both publish for audit
