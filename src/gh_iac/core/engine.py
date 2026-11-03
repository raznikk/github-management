from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Type

import yaml

from gh_iac.core.client import GitHubClient
from gh_iac.core.dag import DependencyGraph
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
    """Core IaC reconciliation engine with DAG concurrency."""

    def __init__(
        self,
        client: GitHubClient,
        state_manager: Optional[StateManager] = None,
        concurrency: int = 5,
    ):
        self.client = client
        self.state_manager = state_manager or StateManager()
        self.concurrency = concurrency
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

        # Sort manifests topologically using DependencyGraph
        if manifests:
            dag = DependencyGraph(manifests)
            tiers = dag.get_execution_tiers()
            # Flatten tiers in topological order
            sorted_manifests: List[GitHubManifest] = []
            for tier in tiers:
                # Secondary sort within tier by priority
                tier.sort(key=lambda m: KIND_PRIORITY.get(m.kind, 999))
                sorted_manifests.extend(tier)
            return sorted_manifests

        return manifests

    def _plan_resource(self, manifest: GitHubManifest) -> ResourcePlan:
        provider = self.get_provider(manifest.kind)
        current_state = provider.read(manifest)
        return provider.plan(manifest, current_state)

    def plan(self, manifests: List[GitHubManifest]) -> List[ResourcePlan]:
        """Compute execution plan against current GitHub state using DAG concurrency."""
        if not manifests:
            return []

        dag = DependencyGraph(manifests)
        tiers = dag.get_execution_tiers()
        plans: List[ResourcePlan] = []

        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            for tier in tiers:
                tier_plans = list(executor.map(self._plan_resource, tier))
                plans.extend(tier_plans)

        return plans

    def _apply_single(self, plan: ResourcePlan, manifest: GitHubManifest) -> ResourceState:
        provider = self.get_provider(plan.kind)
        new_state = provider.apply(plan, manifest)
        self.state_manager.set_resource(new_state.resource_id, new_state)
        return new_state

    def apply(self, plans: List[ResourcePlan], manifests: List[GitHubManifest]) -> List[ResourceState]:
        """Apply planned changes and persist state tier-by-tier."""
        plan_map = {p.resource_id: p for p in plans}
        applied_states: List[ResourceState] = []

        dag = DependencyGraph(manifests)
        tiers = dag.get_execution_tiers()

        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            for tier in tiers:
                tasks = []
                for manifest in tier:
                    plan = plan_map.get(manifest.resource_id)
                    if plan:
                        tasks.append((plan, manifest))

                tier_states = list(executor.map(lambda pair: self._apply_single(*pair), tasks))
                applied_states.extend(tier_states)
                self.state_manager.save()

        return applied_states

