# Makefile — multi-tenant web app only
#
#   make ci              Required before every push
#   make install-hooks   pre-push runs make ci

.PHONY: help ci test lint typecheck install-hooks web-install

help:
	@echo "investment-portfolio-analysis (multi-tenant web)"
	@echo ""
	@echo "  make ci              typecheck + tests + coverage ≥80% + e2e"
	@echo "  make coverage        c8 gate only (unit+api+mcp)"
	@echo "  make test            all web suites (no coverage gate)"
	@echo "  make typecheck       web tsc"
	@echo "  make web-install     npm ci in web/"
	@echo "  make install-hooks   pre-push → make ci"
	@echo "  SKIP_COVERAGE=1      escape hatch for make ci (documented)"
	@echo ""

ci:
	@echo "=== Web: install (if needed) ==="
	@if [ ! -d web/node_modules ]; then (cd web && npm ci); fi
	@echo "=== Web: typecheck + tests + coverage ≥80% ==="
	@if [ "$${SKIP_COVERAGE}" = "1" ]; then \
		echo "WARNING: SKIP_COVERAGE=1 — coverage gate disabled"; \
		cd web && npm run typecheck && npm test; \
	else \
		cd web && npm run ci; \
	fi
	@echo ""
	@echo "✅ CI passed (coverage gate). Safe to push."

test:
	@if [ ! -d web/node_modules ]; then (cd web && npm ci); fi
	cd web && npm test

coverage:
	@if [ ! -d web/node_modules ]; then (cd web && npm ci); fi
	cd web && npm run test:coverage

typecheck:
	@if [ ! -d web/node_modules ]; then (cd web && npm ci); fi
	cd web && npm run typecheck

lint:
	@if [ ! -d web/node_modules ]; then (cd web && npm ci); fi
	cd web && npm run lint

web-install:
	cd web && npm ci

install-hooks:
	@mkdir -p .git/hooks
	@cp scripts/git-hooks/pre-push .git/hooks/pre-push
	@chmod +x .git/hooks/pre-push
	@echo "✅ pre-push hook installed (runs make ci)"
