# =============================================================================
# GitHub IaC Management Engine - Developer Task Runner
# =============================================================================

# Default recipe: display available commands
default:
    @just --list

# -----------------------------------------------------------------------------
# Environment & Setup
# -----------------------------------------------------------------------------

## Install all dependencies including development tools
install:
    uv sync --extra dev

## Install git pre-commit hooks into .git/hooks
pre-commit-install:
    uv run pre-commit install

## Run all pre-commit hooks against all files
pre-commit-run:
    uv run pre-commit run --all-files

# -----------------------------------------------------------------------------
# Code Quality, Formatting & Static Analysis
# -----------------------------------------------------------------------------

## Run all quality checks (linting, format-checking, and static type checking)
check: lint format-check typecheck

## Lint Python source code with Ruff
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
    uv run --extra dev pytest --cov=gh_iac --cov-report=term-missing

## Run tests and generate HTML code coverage report in htmlcov/
cov-html:
    uv run --extra dev pytest --cov=gh_iac --cov-report=html
    @echo "Coverage HTML report generated at htmlcov/index.html"

# -----------------------------------------------------------------------------
# Manifest Validation & CLI Operations
# -----------------------------------------------------------------------------

## Validate declarative manifest schema against Pydantic models
validate path="examples/full_stack.yaml":
    uv run gh-iac validate {{path}}

## Validate all example manifests in repository
validate-all:
    uv run gh-iac validate examples/full_stack.yaml
    uv run gh-iac validate examples/multi_org/

## Run security and governance baseline audits
lint-manifests path="examples/multi_org/":
    uv run gh-iac lint {{path}} --strict

## Compute plan against target environment (ghec / ghes / emu)
plan target="ghec" path="examples/multi_org/":
    uv run gh-iac plan {{path}} --target {{target}}

## Compute plan and output Markdown summary
plan-markdown target="ghec" path="examples/multi_org/":
    uv run gh-iac plan {{path}} --target {{target}} --markdown

## Apply declarative manifests to target environment
apply target="ghec" path="examples/multi_org/":
    uv run gh-iac apply {{path}} --target {{target}} --auto-approve

## Check for out-of-band configuration drift against GitHub
drift target="ghec" path="examples/full_stack.yaml":
    uv run gh-iac drift {{path}} --target {{target}}

# -----------------------------------------------------------------------------
# Build & Cleanup
# -----------------------------------------------------------------------------

## Build python distribution wheel and sdist
build:
    uv build

## Build Docker production container image
docker-build:
    docker build -t gh-iac:latest .

## Clean temporary files, build caches, and test artifacts
clean:
    rm -rf build/ dist/ *.egg-info .pytest_cache/ htmlcov/ .coverage* .ruff_cache/ .mypy_cache/
    find . -type d -name __pycache__ -exec rm -rf {} +
