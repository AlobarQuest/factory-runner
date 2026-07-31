.PHONY: check fix

VENV_BIN := $(CURDIR)/.venv/bin
NODE_BIN := $(CURDIR)/node_modules/.bin
export PATH := $(VENV_BIN):$(NODE_BIN):$(PATH)

RUFF := $(VENV_BIN)/ruff
PYRIGHT := $(VENV_BIN)/pyright
PYTEST := $(VENV_BIN)/pytest

# A missing tool is a hard error, never a skip: a gate that skips is a gate that
# attests. Tools resolve from the repo-local .venv so a global install cannot
# collect against the wrong interpreter.
require = @test -x $(1) || { echo "check: missing $(1) - run 'uv venv --clear && uv sync'"; exit 1; }

# pytest exits 5 when it collects nothing; make propagates that as a failure.
check:
	$(call require,$(RUFF))
	$(call require,$(PYRIGHT))
	$(call require,$(PYTEST))
	$(RUFF) check .
	$(RUFF) format --check .
	$(PYRIGHT)
	$(PYTEST)

fix:
	$(call require,$(RUFF))
	$(RUFF) check --fix .
	$(RUFF) format .
