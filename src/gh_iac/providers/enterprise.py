"""Enterprise construct providers (Policies, EMU Identity/Groups, Audit Streams)."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from gh_iac.core.manifest import GitHubManifest
from gh_iac.core.state import ResourceState
from gh_iac.providers.base import ActionType, BaseProvider, ResourcePlan


class EnterprisePolicyProvider(BaseProvider):
    """
    Manages Enterprise-level policy settings across GHEC, GHES, and EMU.
    Uses GraphQL enterprise node queries and mutations where possible,
    with REST fallback for enterprise policy administration.
    """

    def read(self, manifest: GitHubManifest) -> Optional[ResourceState]:
        enterprise_slug = manifest.metadata.enterprise or manifest.metadata.name

        # 1. Primary GraphQL Query to read Enterprise ID and Policies
        query = """
        query GetEnterpriseInfo($slug: String!) {
          enterprise(slug: $slug) {
            id
            slug
            name
            description
            url
            billingInfo {
              allLicensableUsersCount
            }
          }
        }
        """
        try:
            data = self.client.graphql(query, {"slug": enterprise_slug})
            ent = data.get("enterprise")
            if not ent:
                return None

            # Fetch enterprise settings / policies via REST if needed for advanced settings
            # REST: GET /enterprises/{enterprise}/settings (or actions policies)
            actions_policy = {}
            try:
                actions_policy = self.client.rest(
                    "GET",
                    f"/enterprises/{enterprise_slug}/actions/permissions",
                )
            except Exception:
                pass

            return ResourceState(
                resource_id=manifest.resource_id,
                kind=manifest.kind,
                node_id=ent.get("id"),
                url=ent.get("url"),
                attributes={
                    "name": ent.get("name"),
                    "slug": ent.get("slug"),
                    "description": ent.get("description"),
                    "actions_permissions": actions_policy,
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
        for key, val in desired.items():
            current_val = current.attributes.get(key) or current.applied_spec.get(key)
            if current_val != val:
                diff[key] = {"old": current_val, "new": val}

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
        enterprise_slug = manifest.metadata.enterprise or manifest.metadata.name
        desired = manifest.spec

        # Apply Actions policy if defined in spec (REST endpoint as GitHub has not exposed enterprise action policies in GraphQL)
        if "enabled_repositories" in desired or "allowed_actions" in desired:
            payload = {}
            if "enabled_repositories" in desired:
                payload["enabled_repositories"] = desired["enabled_repositories"]
            if "allowed_actions" in desired:
                payload["allowed_actions"] = desired["allowed_actions"]

            self.client.rest(
                "PUT",
                f"/enterprises/{enterprise_slug}/actions/permissions",
                json_data=payload,
            )

        # Mutate enterprise description/name via GraphQL if possible or REST
        return ResourceState(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            node_id=plan.current_state.get("id") if plan.current_state else None,
            attributes=desired,
            applied_spec=desired,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )


class EMUExternalGroupProvider(BaseProvider):
    """
    Manages GHEC EMU SCIM / External IdP group mappings to GitHub Enterprise teams.
    Prefers SCIM v2 APIs for provisioning external IdP groups.
    """

    def read(self, manifest: GitHubManifest) -> Optional[ResourceState]:
        group_display_name = manifest.metadata.name
        try:
            # SCIM query: GET /scim/v2/enterprises/{enterprise}/Groups?filter=displayName eq "..."
            res = self.client.scim_request(
                "GET",
                "/Groups",
                params={"filter": f'displayName eq "{group_display_name}"'},
            )
            resources = res.get("Resources", []) if isinstance(res, dict) else []
            if not resources:
                return None
            group = resources[0]
            return ResourceState(
                resource_id=manifest.resource_id,
                kind=manifest.kind,
                numeric_id=group.get("id"),
                attributes={
                    "displayName": group.get("displayName"),
                    "externalId": group.get("externalId"),
                    "members": group.get("members", []),
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
        for k, v in desired.items():
            if current.attributes.get(k) != v:
                diff[k] = {"old": current.attributes.get(k), "new": v}

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
        desired = manifest.spec
        if plan.action == ActionType.CREATE:
            payload = {
                "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
                "displayName": manifest.metadata.name,
                "externalId": desired.get("externalId", manifest.metadata.name),
                "members": desired.get("members", []),
            }
            res = self.client.scim_request("POST", "/Groups", json_data=payload)
            numeric_id = res.get("id")
        elif plan.action == ActionType.UPDATE and plan.current_state:
            group_id = plan.current_state.get("numeric_id")
            payload = {
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [
                    {
                        "op": "replace",
                        "path": "displayName",
                        "value": desired.get("displayName", manifest.metadata.name),
                    }
                ],
            }
            res = self.client.scim_request("PATCH", f"/Groups/{group_id}", json_data=payload)
            numeric_id = group_id
        else:
            numeric_id = None

        return ResourceState(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            numeric_id=numeric_id,
            attributes=desired,
            applied_spec=desired,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )
