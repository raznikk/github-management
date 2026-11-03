"""Engine orchestrating manifest parsing, DAG sorting, planning, and execution."""

from pathlib import Path
from typing import Dict, List, Optional, Type

import yaml

from gh_iac.core.client import GitHubClient
from gh_iac.core.manifest import GitHubManifest
from gh_iac.core.state import ResourceState, StateManager
from gh_iac.providers.base import BaseProvider, ResourcePlan
from gh_iac.providers.enterprise import (
    EMUExternalGroupProvider,
    EMUSCIMUserProvider,
    EMUTeamMappingProvider,
    EnterpriseAuditStreamProvider,
    EnterpriseCustomRoleProvider,
    EnterpriseIPAllowListProvider,
    EnterprisePolicyProvider,
    EnterpriseRunnerGroupProvider,
    GitHubAppProvider,
)
from gh_iac.providers.governance import (
    CustomRepositoryRoleProvider,
    EnterpriseSecuritySettingProvider,
)
from gh_iac.providers.organization import (
    OrganizationProvider,
    OrganizationSecretProvider,
    TeamProvider,
)
from gh_iac.providers.repository import (
    RepositoryProvider,
    RepositoryRulesetProvider,
    RepositorySecretProvider,
)

# Priority rank for topological ordering (lower number executes first)
KIND_PRIORITY = {
    # 1. Enterprise constructs
    "EnterprisePolicy": 10,
    "EnterpriseAccount": 10,
    "EnterpriseAuditStream": 15,
    "EnterpriseIPAllowList": 15,
    "EnterpriseRunnerGroup": 15,
    "EMUSCIMUser": 18,
    "EMUExternalGroup": 20,
    "EMUTeamMapping": 25,
    "GitHubApp": 28,
    # 2. Governance constructs
    "EnterpriseSecuritySetting": 30,
    "EnterpriseCustomRole": 35,
    "CustomRepositoryRole": 40,
    # 3. Organization & Team constructs
    "Organization": 50,
    "OrganizationSecret": 55,
    "Team": 60,
    # 4. Repository & Ruleset constructs
    "Repository": 70,
    "RepositorySecret": 75,
    "RepositoryRuleset": 80,
}


PROVIDER_REGISTRY: Dict[str, Type[BaseProvider]] = {
    "EnterprisePolicy": EnterprisePolicyProvider,
    "EnterpriseAccount": EnterprisePolicyProvider,
    "EnterpriseAuditStream": EnterpriseAuditStreamProvider,
    "EnterpriseIPAllowList": EnterpriseIPAllowListProvider,
    "EnterpriseRunnerGroup": EnterpriseRunnerGroupProvider,
    "EMUSCIMUser": EMUSCIMUserProvider,
    "EMUExternalGroup": EMUExternalGroupProvider,
    "EMUTeamMapping": EMUTeamMappingProvider,
    "GitHubApp": GitHubAppProvider,
    "EnterpriseSecuritySetting": EnterpriseSecuritySettingProvider,
    "EnterpriseCustomRole": EnterpriseCustomRoleProvider,
    "CustomRepositoryRole": CustomRepositoryRoleProvider,
    "Organization": OrganizationProvider,
    "OrganizationSecret": OrganizationSecretProvider,
    "Team": TeamProvider,
    "Repository": RepositoryProvider,
    "RepositorySecret": RepositorySecretProvider,
    "RepositoryRuleset": RepositoryRulesetProvider,
}


class Engine:
    """Core IaC reconciliation engine."""

    def __init__(self, client: GitHubClient, state_manager: Optional[StateManager] = None):
        self.client = client
        self.state_manager = state_manager or StateManager()
        self._provider_cache: Dict[str, BaseProvider] = {}

    def get_provider(self, kind: str) -> BaseProvider:
        if kind not in self._provider_cache:
            provider_cls = PROVIDER_REGISTRY.get(kind)
            if not provider_cls:
                raise ValueError(f"No provider registered for construct Kind: '{kind}'")
            self._provider_cache[kind] = provider_cls(self.client)
        return self._provider_cache[kind]

    @staticmethod
    def load_manifests(path: Path) -> List[GitHubManifest]:
        """Load and parse YAML manifests from file or directory recursively."""
        manifests: List[GitHubManifest] = []
        files = [path] if path.is_file() else list(path.glob("**/*.yaml")) + list(path.glob("**/*.yml"))

        for file in files:
            content = file.read_text(encoding="utf-8")
            for doc in yaml.safe_load_all(content):
                if doc and isinstance(doc, dict) and "kind" in doc:
                    manifests.append(GitHubManifest.model_validate(doc))

        # Sort manifests topologically based on construct dependency priority
        manifests.sort(key=lambda m: KIND_PRIORITY.get(m.kind, 999))
        return manifests

    def plan(self, manifests: List[GitHubManifest]) -> List[ResourcePlan]:
        """Compute execution plan against current GitHub state."""
        plans: List[ResourcePlan] = []
        for manifest in manifests:
            provider = self.get_provider(manifest.kind)
            current_state = provider.read(manifest)
            plan = provider.plan(manifest, current_state)
            plans.append(plan)
        return plans

    def apply(self, plans: List[ResourcePlan], manifests: List[GitHubManifest]) -> List[ResourceState]:
        """Apply planned changes and persist state."""
        manifest_map = {m.resource_id: m for m in manifests}
        applied_states: List[ResourceState] = []

        for plan in plans:
            manifest = manifest_map.get(plan.resource_id)
            if not manifest:
                continue

            provider = self.get_provider(plan.kind)
            new_state = provider.apply(plan, manifest)
            self.state_manager.set_resource(new_state.resource_id, new_state)
            applied_states.append(new_state)

        self.state_manager.save()
        return applied_states
