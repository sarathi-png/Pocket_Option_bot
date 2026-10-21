.PHONY: install backend frontend test build dev

install:
	python3 -m venv .venv
	.venv/bin/pip install -r backend/requirements-dev.txt
	npm --prefix frontend install

backend:
	cd backend && ../.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

frontend:
	npm --prefix frontend run dev

test:
	.venv/bin/python -m pytest backend/tests -q
	npm --prefix frontend test
	npm --prefix frontend run typecheck

build:
	npm --prefix frontend run build

dev:
	@echo "Run 'make backend' and 'make frontend' in two terminals."
