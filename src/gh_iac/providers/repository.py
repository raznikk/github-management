"""Repository and Branch Ruleset Providers."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from gh_iac.core.manifest import GitHubManifest
from gh_iac.core.state import ResourceState
from gh_iac.providers.base import ActionType, BaseProvider, ResourcePlan


class RepositoryProvider(BaseProvider):
    """
    Manages GitHub Repositories.
    Prefers GraphQL queries and createRepository/updateRepository mutations.
    """

    def read(self, manifest: GitHubManifest) -> Optional[ResourceState]:
        org = manifest.metadata.organization
        repo_name = manifest.metadata.name
        if not org:
            raise ValueError("Repository construct requires metadata.organization.")

        query = """
        query GetRepo($owner: String!, $name: String!) {
          repository(owner: $owner, name: $name) {
            id
            name
            description
            isPrivate
            hasWikiEnabled
            hasIssuesEnabled
            hasProjectsEnabled
            deleteBranchOnMerge
            defaultBranchRef {
              name
            }
          }
        }
        """
        try:
            data = self.client.graphql(query, {"owner": org, "name": repo_name})
            repo = data.get("repository")
            if not repo:
                return None
            return ResourceState(
                resource_id=manifest.resource_id,
                kind=manifest.kind,
                node_id=repo.get("id"),
                attributes={
                    "name": repo.get("name"),
                    "description": repo.get("description"),
                    "visibility": "private" if repo.get("isPrivate") else "public",
                    "has_wiki": repo.get("hasWikiEnabled"),
                    "has_issues": repo.get("hasIssuesEnabled"),
                    "has_projects": repo.get("hasProjectsEnabled"),
                    "delete_branch_on_merge": repo.get("deleteBranchOnMerge"),
                    "default_branch": (repo.get("defaultBranchRef") or {}).get("name", "main"),
                },
                applied_spec=manifest.spec,
                last_updated=datetime.now(timezone.utc).isoformat(),
            )
        except Exception:
            return None

    def plan(self, manifest: GitHubManifest, current: Optional[ResourceState]) -> ResourcePlan:
        desired = manifest.spec
        if not current:
            return ResourcePlan(
                resource_id=manifest.resource_id,
                kind=manifest.kind,
                action=ActionType.CREATE,
                diff={"desired": desired},
                current_state=None,
                desired_state=desired,
            )

        diff: Dict[str, Any] = {}
        for k in ["description", "visibility", "has_wiki", "has_issues", "delete_branch_on_merge"]:
            if k in desired and current.attributes.get(k) != desired[k]:
                diff[k] = {"old": current.attributes.get(k), "new": desired[k]}

        action = ActionType.UPDATE if diff else ActionType.NOOP
        return ResourcePlan(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            action=action,
            diff=diff,
            current_state=current.attributes,
            desired_state=desired,
        )

    def apply(self, plan: ResourcePlan, manifest: GitHubManifest) -> ResourceState:
        org = manifest.metadata.organization
        repo_name = manifest.metadata.name
        desired = manifest.spec

        node_id = None
        if plan.action == ActionType.CREATE:
            # First try GraphQL createRepository mutation
            owner_query = """
            query GetOrgId($login: String!) {
              organization(login: $login) {
                id
              }
            }
            """
            try:
                org_data = self.client.graphql(owner_query, {"login": org})
                owner_id = (org_data.get("organization") or {}).get("id")
                if owner_id:
                    create_mutation = """
                    mutation CreateRepo($ownerId: ID!, $name: String!, $visibility: RepositoryVisibility!, $description: String) {
                      createRepository(input: {ownerId: $ownerId, name: $name, visibility: $visibility, description: $description}) {
                        repository {
                          id
                        }
                      }
                    }
                    """
                    vis = "PRIVATE" if desired.get("visibility", "private") == "private" else "PUBLIC"
                    res = self.client.graphql(
                        create_mutation,
                        {
                            "ownerId": owner_id,
                            "name": repo_name,
                            "visibility": vis,
                            "description": desired.get("description", ""),
                        },
                    )
                    node_id = res.get("createRepository", {}).get("repository", {}).get("id")
            except Exception:
                # Fallback to REST: POST /orgs/{org}/repos
                rest_payload = {
                    "name": repo_name,
                    "description": desired.get("description", ""),
                    "private": desired.get("visibility", "private") == "private",
                    "has_issues": desired.get("has_issues", True),
                    "has_wiki": desired.get("has_wiki", False),
                    "delete_branch_on_merge": desired.get("delete_branch_on_merge", True),
                }
                res = self.client.rest("POST", f"/orgs/{org}/repos", json_data=rest_payload)
                node_id = res.get("node_id") if isinstance(res, dict) else None

        elif plan.action == ActionType.UPDATE:
            # GraphQL updateRepository mutation
            target_node_id = plan.current_state.get("id") if plan.current_state else None
            if not target_node_id:
                curr = self.read(manifest)
                target_node_id = curr.node_id if curr else None

            if target_node_id:
                update_mutation = """
                mutation UpdateRepo($id: ID!, $description: String) {
                  updateRepository(input: {repositoryId: $id, description: $description}) {
                    repository {
                      id
                    }
                  }
                }
                """
                try:
                    self.client.graphql(
                        update_mutation,
                        {"id": target_node_id, "description": desired.get("description", "")},
                    )
                    node_id = target_node_id
                except Exception:
                    # REST fallback: PATCH /repos/{org}/{repo}
                    res = self.client.rest("PATCH", f"/repos/{org}/{repo_name}", json_data=desired)
                    node_id = res.get("node_id") if isinstance(res, dict) else None

        return ResourceState(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            node_id=node_id,
            attributes=desired,
            applied_spec=desired,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )


class RepositoryRulesetProvider(BaseProvider):
    """
    Manages GitHub modern Repository Rulesets (branch & tag protections).
    GitHub provides ruleset management via REST v3 endpoints:
    /repos/{owner}/{repo}/rulesets
    """

    def read(self, manifest: GitHubManifest) -> Optional[ResourceState]:
        org = manifest.metadata.organization
        repo = manifest.metadata.repository or manifest.metadata.name
        ruleset_name = manifest.spec.get("name", manifest.metadata.name)

        if not org or not repo:
            raise ValueError("RepositoryRuleset requires metadata.organization and metadata.repository.")

        try:
            rulesets = self.client.rest("GET", f"/repos/{org}/{repo}/rulesets")
            if isinstance(rulesets, list):
                for rs in rulesets:
                    if rs.get("name") == ruleset_name:
                        detail = self.client.rest("GET", f"/repos/{org}/{repo}/rulesets/{rs.get('id')}")
                        return ResourceState(
                            resource_id=manifest.resource_id,
                            kind=manifest.kind,
                            numeric_id=rs.get("id"),
                            attributes=detail if isinstance(detail, dict) else rs,
                            applied_spec=manifest.spec,
                            last_updated=datetime.now(timezone.utc).isoformat(),
                        )
            return None
        except Exception:
            return None

    def plan(self, manifest: GitHubManifest, current: Optional[ResourceState]) -> ResourcePlan:
        desired = manifest.spec
        if not current:
            return ResourcePlan(
                resource_id=manifest.resource_id,
                kind=manifest.kind,
                action=ActionType.CREATE,
                diff={"desired": desired},
                current_state=None,
                desired_state=desired,
            )

        diff: Dict[str, Any] = {}
        for k in ["enforcement", "target", "rules"]:
            if k in desired and current.attributes.get(k) != desired[k]:
                diff[k] = {"old": current.attributes.get(k), "new": desired[k]}

        action = ActionType.UPDATE if diff else ActionType.NOOP
        return ResourcePlan(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            action=action,
            diff=diff,
            current_state=current.attributes,
            desired_state=desired,
        )

    def apply(self, plan: ResourcePlan, manifest: GitHubManifest) -> ResourceState:
        org = manifest.metadata.organization
        repo = manifest.metadata.repository or manifest.metadata.name
        desired = manifest.spec

        numeric_id = None
        if plan.action == ActionType.CREATE:
            res = self.client.rest("POST", f"/repos/{org}/{repo}/rulesets", json_data=desired)
            numeric_id = res.get("id") if isinstance(res, dict) else None
        elif plan.action == ActionType.UPDATE:
            ruleset_id = plan.current_state.get("numeric_id") if plan.current_state else None
            if not ruleset_id:
                curr = self.read(manifest)
                ruleset_id = curr.numeric_id if curr else None

            if ruleset_id:
                res = self.client.rest("PUT", f"/repos/{org}/{repo}/rulesets/{ruleset_id}", json_data=desired)
                numeric_id = ruleset_id

        return ResourceState(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            numeric_id=numeric_id,
            attributes=desired,
            applied_spec=desired,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )
