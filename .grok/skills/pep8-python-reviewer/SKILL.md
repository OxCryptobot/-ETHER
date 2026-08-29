---
name: pep8-python-reviewer
description: PEP 8 / Ruff reviewer for Python. Use when user asks to review Python, PEP 8 check, style lint, or readability.
---

# PEP 8 reviewer (ETHER)

Style after green. Never let pep8_review override failing tests.

## Enforce

- Ruff line-length 100, py311.
- AST-parse before disk write.
- No eval/exec/__import__ in generated agent code.
- Type hints on new core modules. Do not reformat core/pipeline.py as a drive-by.
- Tests: pytest -q --tb=short. Do not pull Ollama into unit files.

## Do not

Treat ruff-clean plus exit 0 as correctness (FINDINGS section 3 verification theatre).
