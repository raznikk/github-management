# Justfile for GitHub IaC Management Engine (gh-iac)
set shell := ["bash", "-uc"]
export PATH := env_var('HOME') + "/.local/share/mise/shims:" + env_var('PATH')

# Default recipe: list available recipes
default:
    @just --list

# -----------------------------------------------------------------------------
# Setup & Dependencies
# -----------------------------------------------------------------------------

## Install dependencies and editable package
install:
    uv pip install -e .

## Install development dependencies (pytest, respx, ruff, mypy, pytest-cov)
install-dev:
    uv pip install -e ".[dev]"

# -----------------------------------------------------------------------------
# Code Quality & Linting
# -----------------------------------------------------------------------------

## Run all static code quality checks (ruff + typecheck)
check: lint format-check

## Lint Python code with Ruff
lint:
    uv run ruff check

## Lint and automatically fix fixable issues
lint-fix:
    uv run ruff check --fix

## Format Python code with Ruff
format:
    uv run ruff format

## Check code formatting without making modifications
format-check:
    uv run ruff format --check

## Run static type checking with mypy
typecheck:
    uv run mypy src/gh_iac

# -----------------------------------------------------------------------------
# Testing & Coverage
# -----------------------------------------------------------------------------

## Run all unit and integration tests
test:
    uv run --extra dev pytest

## Run tests with verbose output
test-verbose:
    uv run --extra dev pytest -v

## Run tests and output summary code coverage
cov:
    uv run --extra dev pytest --cov=gh_iac

## Run tests and output line-by-line missing coverage report
cov-report:
    uv run --extra dev pytest --cov=gh_iac --cov-report=term-missing

## Generate interactive HTML coverage report in htmlcov/
cov-html:
    uv run --extra dev pytest --cov=gh_iac --cov-report=html
    @echo "Coverage HTML generated at: file://$(pwd)/htmlcov/index.html"

# -----------------------------------------------------------------------------
# Declarative Manifest Workflows
# -----------------------------------------------------------------------------

## Validate manifest schema (file or directory, default: examples/full_stack.yaml)
validate path="examples/full_stack.yaml":
    uv run gh-iac validate {{path}}

## Validate all example stacks (single-file stack and multi-org directory tree)
validate-all:
    uv run gh-iac validate examples/full_stack.yaml
    uv run gh-iac validate examples/multi_org/

## Lint manifest governance and security rules (default: examples/multi_org/)
lint-manifests path="examples/multi_org/":
    uv run gh-iac lint {{path}} --strict

## Compute dry-run plan (default: target=ghec path=examples/multi_org/)
plan target="ghec" path="examples/multi_org/":
    uv run gh-iac plan {{path}} --target {{target}}

## Compute dry-run plan in machine-readable JSON format
plan-json target="ghec" path="examples/multi_org/":
    uv run gh-iac plan {{path}} --target {{target}} --json

## Compute dry-run plan in GitHub Flavored Markdown format
plan-markdown target="ghec" path="examples/multi_org/":
    uv run gh-iac plan {{path}} --target {{target}} --markdown

## Apply declarative manifests to target environment
apply target="ghec" path="examples/multi_org/":
    uv run gh-iac apply {{path}} --target {{target}} --auto-approve

## Check for out-of-band configuration drift against GitHub
drift target="ghec" path="examples/full_stack.yaml":
    uv run gh-iac drift {{path}} --target {{target}}

# -----------------------------------------------------------------------------
# Documentation (Jekyll & GitHub Pages)
# -----------------------------------------------------------------------------

## Preview Jekyll documentation locally (requires jekyll or bundle)
docs-serve:
    @if command -v bundle >/dev/null 2>&1; then \
        bundle exec jekyll serve; \
    elif command -v jekyll >/dev/null 2>&1; then \
        jekyll serve; \
    else \
        echo "Jekyll not installed locally. Documentation is deployed automatically via GitHub Pages workflow (.github/workflows/pages.yml)."; \
    fi

# -----------------------------------------------------------------------------
# Build & Container Packaging
# -----------------------------------------------------------------------------

## Build python distribution wheel and sdist
build:
    uv build

## Build Docker production container image
docker-build:
    docker build -t gh-iac:latest .

## Clean temporary files, build caches, and test artifacts
clean:
    rm -rf build/ dist/ *.egg-info .pytest_cache/ htmlcov/ .coverage* .ruff_cache/
    find . -type d -name __pycache__ -exec rm -rf {} +
