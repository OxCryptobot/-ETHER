# @ETHER Status

## Honest split

| Layer | Job |
|-------|-----|
| **`stabilize.ps1`** | Bring-up + keep-alive + **prove one learning cycle** |
| **`ether_daemon.py`** | Ongoing autonomy: flywheel, batch, recovery, guardian, dashboard |
| **GitHub runner** | Optional remote dispatch only |

`stabilize` alone is not "learning." It starts the daemon and **runs one smart cycle** so growth is proven, not assumed. After that the daemon keeps cycling (~5 min) without you.

## One command

```powershell
cd C:\Users\Otcde\ETHER
git fetch origin
git reset --hard origin/main
powershell -ExecutionPolicy Bypass -File .\scripts\stabilize.ps1
```

Step 6 may take several minutes on **qwen2.5-coder:3b** (host hardware).

## Self-heal

- Process dead or :8787 closed -> **ETHER-Ensure** every 5 min runs `ensure_daemon.ps1`
- Metrics unhealthy -> daemon `recovery_cycle` (bench/quiz/baseline/guardian)
- Task fail -> auto-enqueue repair with asserts

## Grow / learn

- Curriculum sample + assert nudge
- Sandbox verification_score
- Experience vault + bandit (verified wins only promote)
- Batch drain of repairs

## Hardware (host)

GTX 1650 4GB / 12GB RAM -> **3B only**. No 7B/14B pulls.

## Verify

```powershell
start http://127.0.0.1:8787
Get-Content .\memory\flywheel\latest.json -Head 30
Get-ScheduledTask | Where-Object TaskName -like 'ETHER*'
```
