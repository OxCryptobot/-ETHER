# Windows setup notes

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
python scripts\smoke_test.py
ether doctor
```

Install Docker Desktop and Ollama for Windows for full pipeline support.
