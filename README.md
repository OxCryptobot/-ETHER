# @ETHER

Local-first, self-extending, verified agentic coding system.

## Setup

```bash
# 1. Python
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Docker (for Clear Quartz sandbox)
# Install Docker Desktop / engine and ensure `docker ps` works

# 3. Ollama (for Rose Quartz + embeddings)
# https://ollama.com — then:
ollama pull nomic-embed-text
# ollama pull <your-coder-model>

# 4. Qdrant (optional, for Citrine memory)
docker run -d -p 6333:6333 qdrant/qdrant

# 5. Env
cp .env.example .env   # edit if needed
```

## Usage

```bash
ether status
ether plan "add auth"
ether run "write a function that reverses a string"
ether run "..." --json
ether audit path/to/file.py
ether index ./src
ether search "authentication helper"
pytest
bash scripts/run_tests.sh
```

## Architecture

8 gems · typed Envelope protocol · state machine · Docker sandbox as security boundary.

See [STATUS.md](STATUS.md).
