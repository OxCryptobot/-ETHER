# HOST_START: the one way to run the 1650 writer

**Writer:** `scripts/host_main.py` (`tick()`), on the GTX 1650 Windows host (`C:\Users\Otcde\ETHER`).
**Model:** `qwen3.5:4b-q4_K_M` through Ollama. One model loaded, one request at a time.
**Start method:** one Scheduled Task, `ETHER-Host`. There is no `ETHER.exe`, no daemon task, no VBS, no PowerShell launcher.

```
ETHER-Host task (logon + boot + every 5 min, IgnoreNew, restart-on-failure)
  -> .venv\Scripts\pythonw.exe scripts\host_supervisor.py   (OS lock artifacts\host.lock: never two copies)
       each cycle: fix stale .git\index.lock -> git pull --ff-only -> ensure `ollama serve`
                   -> child: python -m scripts.host_main  (tick lock artifacts\tick.lock, 30 min timeout)
                        -> mark_alive (app_alive.json), self_heal, attach, drain LIVE FIFO,
                           next_goal + honest SOTA batch, day_learn, publish to origin
       crash/timeout -> backoff 15s, 30s, 60s ... 900s max; supervisor updated -> relaunch fresh copy
GitHub autonomy-host.yml (optional, every 15 min) -> scripts/host_ctl.py ci
       supervisor alive -> do nothing | stopped by operator -> do nothing | dead -> schtasks /Run ETHER-Host
       (an inline host_main tick runs only while ETHER-Host is not installed yet)
```

## Why a local task and not the runner

`config/UNIFIED.md` says "GitHub autonomy-host is optional. Queued Actions is not LIVE." The runner path
(which did keep the host ticking on 2026-11-19) has these limits:
- GitHub cron is best effort: it can be late or skipped.
- Ticks run code from the Actions checkout, and the old tick hard-reset `C:\Users\Otcde\ETHER` to origin/main.
- The runner kills child processes when a job ends, so `ollama serve` never stayed up (app_alive `ollama:false`), and LIVE needs Ollama.
- On origin, 20 SOTA goals are marked kept in `sota.json` but their code is not in the files.

The local task keeps working when GitHub is late, holds Ollama in a long-lived parent, and never resets.
The runner stays as a remote "make sure it runs" switch only.

## Install (once, on the 1650)

The fix has to be on **origin/main** first. Today every runner tick runs origin's `host_main.py`, and that
version hard-resets `C:\Users\Otcde\ETHER` to origin/main, so a branch checked out only on the PC gets wiped
within 15 minutes.

1. Get the branch onto origin/main. Either merge the PR, or push the bundle from a machine with a token:
   ```bat
   git fetch ether-host-start.bundle ether-host-start:ether-host-start
   git push origin ether-host-start:main
   ```
2. On the 1650, in `cmd.exe` (not admin):
   ```bat
   cd /d C:\Users\Otcde\ETHER
   git fetch origin && git merge --ff-only origin/main
   scripts\install_host.cmd
   ```
   `install_host.cmd` is idempotent and does all of this:
   - creates `.venv` if it's missing (`host.cmd setup`)
   - deletes the legacy tasks ETHER-Daemon, ETHER-Ensure, ETHER-keepalive, ETHER-keepalive-5m, ETHER-keepalive-boot and the others listed in `host_ctl.LEGACY_TASKS`
   - ends old keepalive, daemon and ether_host processes
   - renames Startup-folder `ETHER*.vbs` and `ETHER*.lnk` to `*.retired`
   - registers `ETHER-Host` from a generated XML (all paths derived from the checkout, nothing hardcoded)
   - starts the task and prints `status`
3. Optional, so it runs before anyone logs on: from an **admin** cmd, run `scripts\install_host.cmd --boot`.
   This registers the task as S4U.

## Daily commands (people and bots)

| Command | Effect |
|---|---|
| `scripts\host.cmd status` | JSON: task installed, supervisor running and pid, cycle, failures, app_alive age, **LIVE verdict**, Ollama now, next_goal, HEAD |
| `scripts\host.cmd start` | clears the stop file, then `schtasks /Run ETHER-Host` (or a direct hidden spawn), and waits until the lock is held |
| `scripts\host.cmd stop` | sticky stop: writes `artifacts\host.stop`, waits up to 90 s for the current pass, then forces |
| `scripts\host.cmd restart` | stop + start |
| `scripts\host.cmd once` | one writer pass in the foreground (debug) |
| `scripts\host.cmd setup` | venv + `pip install -e .` (no reset, no killing) |
| `scripts\host.cmd uninstall` | stop + delete ETHER-Host |

A remote bot (with the user's computer connected and local commands approved) needs exactly one call:
`C:\Users\Otcde\ETHER\scripts\host.cmd start`, then `...\host.cmd status`.

## What "up" means (no training wheels)

LIVE means `app_alive.ts` is under 6 h old **and** Ollama is up. A running supervisor or an open window is not
LIVE. `supervisor.json` is the supervisor's own heartbeat. It is published, but it never stands in for app_alive.

## Ranked options for "running as soon as we call on it"

| Rank | Option | Robustness | Speed to running | Needs |
|---|---|---|---|---|
| 1 | **ETHER-Host task + `--boot` (S4U)** | survives reboot without logon, crash (restart-on-failure + 5-min ensure), self-update (relaunch) | at boot +1 min | admin prompt once |
| 2 | **ETHER-Host task (default, InteractiveToken)** | survives crash and self-update; after reboot it starts at logon | at logon; ensure within 5 min | nothing (no admin) |
| 3 | `host.cmd start` from a bot via the connected computer | instant on demand, same supervisor | seconds | PC on, Grok Bot app connected, command approved |
| 4 | `autonomy-host` workflow_dispatch (`host_ctl.py ci`) | starts the task remotely when the runner is up | GitHub queue, about 1-15 min | runner online |
| 5 | Windows auto-logon + option 2 | like 1, without S4U | at boot | stores a password in the registry (not recommended) |

Options 3 and 4 trigger the same ETHER-Host task. They are switches, not extra writers.

## Self-repair inside single-writer rules

- OS file locks (not pid files): a crashed process can never leave a stale lock.
- `tick.lock` serialises every caller of `host_main.tick` (supervisor, legacy runner tick, old daemon).
- self-heal never deletes `ETHER-Host`, `ETHER-RunnerWatch` or `ETHER-Runner` (`self_heal.PROTECTED_TASKS`,
  enforced by a test). It deletes the legacy starters every tick.
- A stale `.git\index.lock` (over 10 min old) is removed before each pull.
- There is no `git reset --hard` in host_main. `sync_writer` rebases and keeps unpublished kept edits.

## Cadence and publish (batch 2)

- Empty queue: the supervisor backs off 60 s, 120 s, 240 s ... up to
  `ETHER_IDLE_MAX_S` (900 s) instead of re-running a pass every 12 s.
  `artifacts/supervisor.json` shows `state: idle` and `dry_streak`.
- Heartbeat-only publishes go out at most every `ETHER_PUBLISH_MIN_S` (300 s).
  A kept edit (a dirty code path in the publish set) is pushed at once.
  Before batch 2 the host pushed a commit roughly every 20 s (116 commits
  17:13-17:51 ET on 2026-11-19).
- The worktree publish never copies a code file over a newer origin/main
  version (`skipped_code` in `git_push.json`); this used to revert real fixes.
- The supervisor reloads itself when `scripts/host_supervisor.py` changes on
  pull, so batch 2 needs no reinstall.

## Verified on Linux vs needs the 1650

Verified on Linux (pytest):
- singleton lock
- backoff growth and cap
- heartbeat file
- child pass argv and env (`-m scripts.host_main`, `ETHER_SUPERVISOR=1`, no `GITHUB_ACTIONS`)
- sticky stop, relaunch-on-self-update, stale index.lock repair, tick lock
- task XML content, written as UTF-16
- legacy task list, and the self-heal protected list
- start/stop/ci logic with a fake `schtasks`
- SOTA queue refill

Needs the Windows host:
- `schtasks /Create /XML` accepting the XML (the BootTrigger with InteractiveToken falls back to no boot trigger if refused)
- S4U `--boot`
- `msvcrt` locking and `pythonw` behaviour
- the `Get-CimInstance` legacy-process scan
- Ollama staying up under the supervisor and fitting in 4 GB VRAM
- a fresh `app_alive` with `ollama:true` published to origin
