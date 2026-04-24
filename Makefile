.PHONY: lint lint-fix typecheck typecheck-api typecheck-worker typecheck-shared check

UV := uv
REPO_UV_CACHE_DIR := $(CURDIR)/.uv-cache
USE_REPO_UV_CACHE := $(shell cache_root="$${XDG_CACHE_HOME:-$$HOME/.cache}"; if [ -d "$$cache_root/uv" ]; then [ -w "$$cache_root/uv" ] && printf no || printf yes; elif [ -d "$$cache_root" ]; then [ -w "$$cache_root" ] && printf no || printf yes; elif [ -n "$$HOME" ] && [ -d "$$HOME" ]; then [ -w "$$HOME" ] && printf no || printf yes; else printf yes; fi)

ifeq ($(strip $(UV_CACHE_DIR)),)
ifeq ($(USE_REPO_UV_CACHE),yes)
UV_RUN_ENV := UV_CACHE_DIR=$(REPO_UV_CACHE_DIR)
endif
else
UV_RUN_ENV := UV_CACHE_DIR=$(UV_CACHE_DIR)
endif

RUN_LINT := $(UV_RUN_ENV) $(UV) run --group lint
RUN_TYPECHECK := $(UV_RUN_ENV) $(UV) run --group typecheck
RUFF := $(RUN_LINT) ruff
PYRIGHT := $(RUN_TYPECHECK) pyright

lint:
	$(RUFF) check apps packages

lint-fix:
	$(RUFF) check --fix apps packages

typecheck: typecheck-api typecheck-worker typecheck-shared

typecheck-api:
	$(PYRIGHT) --project pyproject.toml apps/api/app apps/api/main.py

typecheck-worker:
	$(PYRIGHT) --project pyproject.toml apps/worker/app apps/worker/worker.py

typecheck-shared:
	$(PYRIGHT) --project pyproject.toml packages/shared-python/shared

check: lint typecheck
