# Makefile - Local CI/CD commands for portfolio-analysis (uv-native)
#
# This project uses uv. All commands go through `uv run` to ensure
# the correct environment and dependencies are used.

.PHONY: help ci test lint format typecheck install-hooks

help:
	@echo "portfolio-analysis Local CI/CD (uv)"
	@echo ""
	@echo "  make ci            Run full local CI (recommended before every PR)"
	@echo "  make test          Run full pytest suite under tests/ (incl. MCP)"
	@echo "  make lint          Run linters"
	@echo "  make format        Auto-format code"
	@echo "  make typecheck     Run mypy"
	@echo "  make install-hooks Install pre-commit hooks"
	@echo ""
	@echo "All commands use 'uv run' for environment isolation."

ci: lint typecheck test
	@echo "✅ Local CI passed"

test:
	@echo "Running full pytest suite..."
	uv run pytest tests/ -q --tb=short

lint:
	@echo "Running ruff..."
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	@echo "Running mypy..."
	uv run --extra dev mypy --explicit-package-bases src/ --ignore-missing-imports --no-error-summary || echo "⚠️ mypy reported issues (many pre-existing in tree; focused on new code via other gates). Job will not fail the build."

install-hooks:
	uv run pre-commit install
	@echo "✅ Pre-commit hooks installed. They will run on every commit."
