# @ETHER

**Local-first, self-extending, verified agentic coding system**

## Core Pillars

1. **Modular Intelligence** — 8 specialized gems with strongly-typed interfaces
2. **Verified Execution** — Every code artifact is sandboxed, tested, and scored before the user sees it
3. **Controlled Evolution** — The system can extend itself via template-based tool generation under human approval

## Architecture

```
User / CLI
    ↓
Orchestrator (state machine)
    ↓
Registry (dispatch)
    ↓
┌──────────────────────────────────────┐
│  Clear Quartz   │  Rose Quartz    │  Citrine        │
│  (Sandbox)      │  (Router)       │  (Memory)       │
├──────────────────────────────────────┤
│  Selenite       │  Amethyst       │  Black Tourmaline│
│  (Planner)      │  (Evolution)    │  (Security)      │
├──────────────────────────────────────┤
│  Labradorite    │  Grandidierite  │                  │
│  (Profiler)     │  (Meta-Extension)│                  │
└──────────────────────────────────────┘
```

## Current Status (v0.1.0)

| Component              | Status |
|------------------------|--------|
| Core schemas           | ✅     |
| Orchestrator           | ✅     |
| Registry               | ✅     |
| Clear Quartz           | ✅ Basic |
| Rose Quartz            | ✅ Basic |
| Citrine                | ✅ Basic |
| Selenite               | ✅ Basic |
| Amethyst               | ✅ Basic |
| Black Tourmaline       | ✅ Basic |
| Labradorite            | ✅ Basic |
| Grandidierite          | ✅ Basic |
| CLI                    | ✅ Working |

## Quick Start

```bash
git clone https://github.com/OxCryptobot/-ETHER.git
cd -ETHER
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e .

ether version
ether status
ether plan "add user authentication"
ether run-gem selenite --prompt "fix the login bug"
```

## Requirements

- Python 3.11+
- Docker (for Clear Quartz sandbox)
- Ollama (for Rose Quartz local inference)
- Qdrant (optional, for Citrine memory)

## Design Principles

- Interfaces first
- Sandbox is the real security boundary
- Fail closed
- Human-in-the-loop for mutation (Grandidierite)
- Local-first

## License

MIT
