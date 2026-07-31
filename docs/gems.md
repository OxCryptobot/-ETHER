# Gems Index

| Gem | Path | Role |
|-----|------|------|
| Clear Quartz | `gems/clear_quartz/` | Sandbox execution |
| Rose Quartz | `gems/rose_quartz/` | LLM routing |
| Citrine | `gems/citrine/` | Memory / retrieval (Qdrant) |
| Selenite | `gems/selenite/` | Planning (consumes critique lessons) |
| Amethyst | `gems/amethyst/` | Logging / evolution |
| Black Tourmaline | `gems/black_tourmaline/` | Security audit |
| Labradorite | `gems/labradorite/` | **Essential** critique & review |
| Grandidierite | `gems/grandidierite/` | Tool generation |

## Infinity topology (self-improvement loop)

```
                 ┌──────────────────────────────────────┐
                 │           memory bus (Citrine +       │
                 │           memory/bus/*.jsonl)         │
                 └───────────────▲──────────────────────┘
                                 │ lessons
    Selenite ──► Rose Quartz ──► Clear Quartz ──► Black Tourmaline
        ▲              │               │                  │
        │              │               │                  ▼
        │              │               │            Labradorite
        │              │               │           (critique ALWAYS)
        │              │               │                  │
        └──────────────┴───────────────┴──── Amethyst ◄───┘
                         (log + bandit RL signal)
```

Rules:

1. **Labradorite is not optional** — every verified run is reviewed.
2. Critiques write to the **memory bus** and optionally Citrine (`patterns` / `failures`).
3. **Selenite** reads prior lessons before planning the next run.
4. **Amethyst** logs outcomes for bandit / experience (RL-style arm credit stays in Pipeline).
5. Test opt-out only: `ETHER_SKIP_CRITIQUE=1`.
