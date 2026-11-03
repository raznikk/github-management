"""Pre-flight Linter and Schema Validation for GitHub IaC manifests."""

import re
from enum import Enum
from typing import List

from pydantic import BaseModel

from gh_iac.core.manifest import GitHubManifest


class LintLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class LintDiagnostic(BaseModel):
    rule_id: str
    level: LintLevel
    message: str
    resource_id: str
    kind: str


class Linter:
    """Evaluates declarative manifests against security, governance, and syntax rules."""

    REPO_NAME_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.]+$")

    def lint(self, manifests: List[GitHubManifest]) -> List[LintDiagnostic]:
        diagnostics: List[LintDiagnostic] = []

        ruleset_repos = set()
        for m in manifests:
            if m.kind == "RepositoryRuleset":
                repo = m.metadata.repository or (m.spec.get("repository") if m.spec else None)
                org = m.metadata.organization
                if repo and org:
                    ruleset_repos.add(f"{org}/{repo}".lower())

        for m in manifests:
            # 1. Naming Constraints
            if m.kind == "Repository":
                if not self.REPO_NAME_REGEX.match(m.metadata.name):
                    diagnostics.append(
                        LintDiagnostic(
                            rule_id="NAM001",
                            level=LintLevel.ERROR,
                            message=f"Invalid repository name '{m.metadata.name}'. Only alphanumeric characters, hyphens, underscores, and dots are permitted.",
                            resource_id=m.resource_id,
                            kind=m.kind,
                        )
                    )

                # 2. Secret Scanning & Push Protection
                spec = m.spec or {}
                if spec.get("secret_scanning_push_protection") is False:
                    diagnostics.append(
                        LintDiagnostic(
                            rule_id="SEC002",
                            level=LintLevel.WARNING,
                            message="Secret scanning push protection is explicitly disabled. Developers might push unencrypted secrets.",
                            resource_id=m.resource_id,
                            kind=m.kind,
                        )
                    )

                # 3. Public Repository GHAS Baseline
                if spec.get("visibility") == "public" and spec.get("advanced_security") is False:
                    diagnostics.append(
                        LintDiagnostic(
                            rule_id="SEC001",
                            level=LintLevel.WARNING,
                            message="GitHub Advanced Security (GHAS) is disabled on a public repository.",
                            resource_id=m.resource_id,
                            kind=m.kind,
                        )
                    )

                # 4. Branch Protection / Ruleset coverage
                if m.metadata.organization:
                    repo_key = f"{m.metadata.organization}/{m.metadata.name}".lower()
                    if repo_key not in ruleset_repos:
                        diagnostics.append(
                            LintDiagnostic(
                                rule_id="GOV001",
                                level=LintLevel.WARNING,
                                message=f"No branch protection ruleset found for repository '{m.resource_id}'. Direct unreviewed pushes may be permitted.",
                                resource_id=m.resource_id,
                                kind=m.kind,
                            )
                        )

            # 5. Organization Governance (2FA)
            elif m.kind == "Organization":
                spec = m.spec or {}
                if spec.get("requiresTwoFactorAuthentication") is False:
                    diagnostics.append(
                        LintDiagnostic(
                            rule_id="GOV002",
                            level=LintLevel.WARNING,
                            message=f"Two-factor authentication is not enforced for organization '{m.metadata.name}'.",
                            resource_id=m.resource_id,
                            kind=m.kind,
                        )
                    )

        return diagnostics
