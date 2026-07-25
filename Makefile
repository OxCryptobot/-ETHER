.PHONY: install test smoke status run

install:
	pip install -e ".[dev]"

test:
	pytest -q

smoke:
	python scripts/smoke_test.py

status:
	ether status

run:
	ether run "$(OBJ)"
