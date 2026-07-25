.PHONY: install test smoke status doctor run

install:
	pip install -e ".[dev]"

test:
	pytest -q

smoke:
	python scripts/smoke_test.py

status:
	ether status

doctor:
	ether doctor

run:
	ether run "$(OBJ)"
