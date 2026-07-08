.PHONY: check fix

VENV_BIN := $(CURDIR)/.venv/bin
NODE_BIN := $(CURDIR)/node_modules/.bin
export PATH := $(VENV_BIN):$(NODE_BIN):$(PATH)

check:
	@if command -v ruff >/dev/null 2>&1; then ruff check .; else echo "ruff not installed - skipping ruff check"; fi
	@if command -v ruff >/dev/null 2>&1; then ruff format --check .; else echo "ruff not installed - skipping ruff format check"; fi
	@if command -v pyright >/dev/null 2>&1; then pyright; else echo "pyright not installed - skipping pyright"; fi
	@if command -v pytest >/dev/null 2>&1; then pytest; else echo "pytest not installed - skipping tests"; fi

fix:
	@if command -v ruff >/dev/null 2>&1; then ruff check --fix .; else echo "ruff not installed - skipping ruff fix"; fi
	@if command -v ruff >/dev/null 2>&1; then ruff format .; else echo "ruff not installed - skipping ruff format"; fi
