"""Directed Acyclic Graph (DAG) and topological concurrency engine."""

from collections import defaultdict
from typing import Dict, List, Set

from gh_iac.core.manifest import GitHubManifest


class CyclicDependencyError(Exception):
    """Raised when circular dependencies exist between resource manifests."""

    pass


class DependencyGraph:
    """
    Constructs and topologically sorts resource dependencies into parallel execution tiers.
    """

    def __init__(self, manifests: List[GitHubManifest]):
        self.manifests = manifests
        self.manifest_map: Dict[str, GitHubManifest] = {m.resource_id: m for m in manifests}
        self.short_keys: Dict[str, str] = {}
        for m in manifests:
            # Map simple keys like "Repository/repo-a" to full resource_id
            simple_key = f"{m.kind}/{m.metadata.name}"
            self.short_keys[simple_key] = m.resource_id

    def _resolve_key(self, key: str) -> str:
        """Resolve either full resource_id or simplified Kind/name key."""
        if key in self.manifest_map:
            return key
        if key in self.short_keys:
            return self.short_keys[key]
        return key

    def _infer_dependencies(self, m: GitHubManifest) -> Set[str]:
        """Infer parent resource dependencies based on hierarchy and explicit labels."""
        deps: Set[str] = set()

        # 1. Repository-scoped resources depend on the parent Repository
        if m.metadata.repository and m.kind not in ("Repository",):
            for res_id, other in self.manifest_map.items():
                if (
                    other.kind == "Repository"
                    and other.metadata.name == m.metadata.repository
                    and other.metadata.organization == m.metadata.organization
                ):
                    deps.add(res_id)

        # 2. Org-scoped resources depend on the parent Organization
        if m.metadata.organization and m.kind not in ("Organization",):
            for res_id, other in self.manifest_map.items():
                if other.kind == "Organization" and other.metadata.name == m.metadata.organization:
                    deps.add(res_id)

        # 3. Enterprise-scoped resources depend on EnterprisePolicy / EnterpriseAccount
        if m.metadata.enterprise and m.kind not in ("EnterprisePolicy", "EnterpriseAccount"):
            for res_id, other in self.manifest_map.items():
                if other.kind in ("EnterprisePolicy", "EnterpriseAccount") and (
                    other.metadata.enterprise == m.metadata.enterprise
                    or other.metadata.name == m.metadata.enterprise
                ):
                    deps.add(res_id)

        # 4. Explicit depends_on declared in labels
        explicit = m.metadata.labels.get("depends_on") or m.metadata.labels.get("dependsOn")
        if explicit:
            for dep_item in explicit.split(","):
                resolved = self._resolve_key(dep_item.strip())
                if resolved in self.manifest_map:
                    deps.add(resolved)

        return deps

    def get_execution_tiers(self) -> List[List[GitHubManifest]]:
        """
        Topologically sort resources into execution tiers (batches).
        Resources within the same tier have no inter-dependencies and can be executed concurrently.
        Raises CyclicDependencyError if circular dependencies are detected.
        """
        adj: Dict[str, Set[str]] = defaultdict(set)
        in_degree: Dict[str, int] = {m.resource_id: 0 for m in self.manifests}

        for m in self.manifests:
            deps = self._infer_dependencies(m)
            for parent_id in deps:
                if parent_id in in_degree and parent_id != m.resource_id:
                    adj[parent_id].add(m.resource_id)
                    in_degree[m.resource_id] += 1

        tiers: List[List[GitHubManifest]] = []
        processed_count = 0
        current_in_degree = dict(in_degree)

        while True:
            # Find all nodes with 0 in-degree in current graph
            current_tier_ids = [res_id for res_id, deg in current_in_degree.items() if deg == 0]
            if not current_tier_ids:
                break

            tier_manifests: List[GitHubManifest] = []
            for res_id in current_tier_ids:
                tier_manifests.append(self.manifest_map[res_id])
                processed_count += 1
                del current_in_degree[res_id]

            # Decrease in-degree for dependents
            for parent_id in current_tier_ids:
                for child_id in adj[parent_id]:
                    if child_id in current_in_degree:
                        current_in_degree[child_id] -= 1

            tiers.append(tier_manifests)

        if processed_count < len(self.manifests):
            raise CyclicDependencyError(
                f"Cyclic dependency detected among resources: {list(current_in_degree.keys())}"
            )

        return tiers
