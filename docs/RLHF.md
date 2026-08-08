# Offline RLHF on ETHER

Teacher → apprentice. Reality, not slides.

## What runs on the host

```
scoreboard_*.json
        │
        ▼
record_preferences_from_scoreboard()
        │
        ├── preferences.jsonl   (preferred vs rejected pairs)
        ├── strategy_stats.json (wins / n per arm)
        └── artifacts/* mirror  (visible on origin after push)
                │
                ▼
live_strategy_boost(strategy)
                │
                ▼
experience.retrieve() ranks few-shots by overlap × boost
```

## Commands

```text
python -m core.preference                  # rlhf_tick: discover + pairs + assert
pytest tests/test_preference_rlhf.py -q
```

## Tricks of the trade

| Trick | Why |
|-------|-----|
| Pair only non-infra failures | Infra is host health, not code skill |
| Min score gap 0.15 | Near-ties are noise |
| Live boost only after n≥3 | One lucky win must not dominate prior |
| Mirror under artifacts/ | memory/ is gitignored; teacher reads origin |
| Same-mutation ranking | Even all-fail boards teach relative quality |
| DPO helper ready | Use when local logprobs exist; until then bandit on strategies |

## Not in scope (yet)

- Full PPO on the base coder every night
- Human click UI for pairwise labels (teacher uses lessons + scoreboards instead)
- Reward model neural net (strategy_stats is the lightweight RM)

## Lessons

- `022_offline_rlhf` — doctrine above
- `016_learn_from_scoreboards` — earlier preference seed
- `006` / `009` — gates that keep the dataset clean

Shipped by Grok 2026-08-08 so the bird flies with a real feedback loop.
