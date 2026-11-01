# GitHub IaC Management Engine

A declarative Infrastructure-as-Code (IaC) management system for GitHub, supporting **GitHub Enterprise Cloud (GHEC)**, **GitHub Enterprise Server (GHES)**, and **GHEC Enterprise Managed Users (EMU)**.

## Key Features

- **GraphQL-First Engine**: Uses GitHub GraphQL API v4 as primary communication layer for high performance and atomic transactions, with seamless dynamic fallback to REST v3 for endpoints not yet available in GraphQL (e.g. SCIM APIs, EMU groups).
- **Comprehensive GitHub Constructs**:
  1. **Enterprise**: Policies, licenses, audit streams, EMU SAML/SCIM mappings.
  2. **Governance & Security**: Custom repository & org roles, GitHub Advanced Security (GHAS), secret scanning, code scanning default setups.
  3. **Organization & Team**: Organizations, teams, membership, IdP group synchronization, rulesets, secrets, and variables.
  4. **Repository & Branch**: Repositories, branch rulesets, environments, deploy keys, Actions permissions.
- **Declarative Manifests**: Kubernetes-style declarative manifests with schema validation (`apiVersion: github.iac/v1alpha1`).
- **Diff, Plan & Apply Cycles**: Dry-run planning with rich terminal diffs and state management.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## CLI Usage

```bash
# Validate manifests
gh-iac validate examples/

# Plan changes against GitHub target
gh-iac plan examples/ --target ghec

# Apply desired state
gh-iac apply examples/ --target ghec
```
