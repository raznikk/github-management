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


class EMUTeamMappingProvider(BaseProvider):
    """
    Manages linking between an external IdP (SAML/SCIM) group and an organization team.
    REST: /orgs/{org}/teams/{team_slug}/external-groups
    """

    def read(self, manifest: GitHubManifest) -> Optional[ResourceState]:
        org = manifest.metadata.organization
        team_slug = manifest.spec.get("team_slug")
        group_id = manifest.spec.get("group_id")
        if not org or not team_slug:
            return None

        try:
            res = self.client.rest("GET", f"/orgs/{org}/teams/{team_slug}/external-groups")
            groups = res.get("groups", []) if isinstance(res, dict) else []
            for g in groups:
                if g.get("group_id") == group_id:
                    return ResourceState(
                        resource_id=manifest.resource_id,
                        kind=manifest.kind,
                        numeric_id=g.get("group_id"),
                        attributes={
                            "team_slug": team_slug,
                            "group_id": g.get("group_id"),
                            "group_name": g.get("group_name"),
                        },
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
        org = manifest.metadata.organization
        team_slug = manifest.spec.get("team_slug")
        group_id = manifest.spec.get("group_id")

        res = self.client.rest(
            "PATCH",
            f"/orgs/{org}/teams/{team_slug}/external-groups",
            json_data={"group_id": group_id},
        )
        return ResourceState(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            numeric_id=group_id,
            attributes={
                "team_slug": team_slug,
                "group_id": group_id,
                "group_name": res.get("group_name") if isinstance(res, dict) else None,
            },
            applied_spec=manifest.spec,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )


class EnterpriseAuditStreamProvider(BaseProvider):
    """
    Manages Enterprise audit log streaming endpoints (S3, Splunk, Azure, Datadog, GCS).
    REST: /enterprises/{enterprise}/audit-log/streams
    """

    def read(self, manifest: GitHubManifest) -> Optional[ResourceState]:
        ent = manifest.metadata.enterprise or manifest.metadata.name
        stream_type = manifest.spec.get("stream_type")
        try:
            streams = self.client.rest("GET", f"/enterprises/{ent}/audit-log/streams")
            if not isinstance(streams, list):
                return None
            for s in streams:
                if s.get("stream_type") == stream_type or s.get("name") == manifest.metadata.name:
                    return ResourceState(
                        resource_id=manifest.resource_id,
                        kind=manifest.kind,
                        numeric_id=s.get("id"),
                        attributes=s,
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
        ent = manifest.metadata.enterprise or manifest.metadata.name
        desired = manifest.spec

        if plan.action == ActionType.CREATE:
            res = self.client.rest(
                "POST",
                f"/enterprises/{ent}/audit-log/streams",
                json_data=desired,
            )
            stream_id = res.get("id") if isinstance(res, dict) else None
        elif plan.action == ActionType.UPDATE and plan.current_state:
            stream_id = plan.current_state.get("id") or plan.current_state.get("numeric_id")
            res = self.client.rest(
                "PUT",
                f"/enterprises/{ent}/audit-log/streams/{stream_id}",
                json_data=desired,
            )
        else:
            stream_id = None
            res = desired

        attributes = dict(desired)
        if isinstance(res, dict):
            attributes.update(res)

        return ResourceState(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            numeric_id=stream_id,
            attributes=attributes,
            applied_spec=desired,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )


class EnterpriseIPAllowListProvider(BaseProvider):
    """
    Manages Enterprise IP Allow List entries via GraphQL.
    Query: GetEnterpriseIPAllowList
    Mutation: CreateIpAllowListEntry
    """

    def read(self, manifest: GitHubManifest) -> Optional[ResourceState]:
        ent_slug = manifest.metadata.enterprise or manifest.metadata.name
        desired_val = manifest.spec.get("allow_list_value")

        query = """
        query GetEnterpriseIPAllowList($slug: String!) {
          enterprise(slug: $slug) {
            id
            ownerInfo {
              ipAllowListEntries(first: 100) {
                nodes {
                  id
                  name
                  allowListValue
                  isActive
                }
              }
            }
          }
        }
        """
        try:
            data = self.client.graphql(query, {"slug": ent_slug})
            ent = data.get("enterprise")
            if not ent:
                return None
            entries = ent.get("ownerInfo", {}).get("ipAllowListEntries", {}).get("nodes", [])
            for entry in entries:
                if entry.get("allowListValue") == desired_val or entry.get("name") == manifest.metadata.name:
                    return ResourceState(
                        resource_id=manifest.resource_id,
                        kind=manifest.kind,
                        node_id=entry.get("id"),
                        attributes=entry,
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

        if plan.action == ActionType.UPDATE and plan.current_state:
            entry_id = plan.current_state.get("id") or (plan.current_state.get("node_id") if hasattr(plan, "current_state") else None)
            if not entry_id:
                # Re-query
                curr = self.read(manifest)
                entry_id = curr.node_id if curr else ""

            mutation = """
            mutation UpdateIpAllowListEntry($input: UpdateIpAllowListEntryInput!) {
              updateIpAllowListEntry(input: $input) {
                ipAllowListEntry {
                  id
                  name
                  allowListValue
                  isActive
                }
              }
            }
            """
            input_payload = {
                "ipAllowListEntryId": entry_id,
                "allowListValue": desired.get("allow_list_value"),
                "name": desired.get("name", manifest.metadata.name),
                "isActive": desired.get("is_active", True),
            }
            data = self.client.graphql(mutation, {"input": input_payload})
            entry = data.get("updateIpAllowListEntry", {}).get("ipAllowListEntry", {})
        else:
            mutation = """
            mutation CreateIpAllowListEntry($input: CreateIpAllowListEntryInput!) {
              createIpAllowListEntry(input: $input) {
                ipAllowListEntry {
                  id
                  name
                  allowListValue
                  isActive
                }
              }
            }
            """
            input_payload = {
                "ownerId": plan.current_state.get("enterprise_id", "") if plan.current_state else "",
                "allowListValue": desired.get("allow_list_value"),
                "name": desired.get("name", manifest.metadata.name),
                "isActive": desired.get("is_active", True),
            }
            data = self.client.graphql(mutation, {"input": input_payload})
            entry = data.get("createIpAllowListEntry", {}).get("ipAllowListEntry", {})

        return ResourceState(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            node_id=entry.get("id"),
            attributes=entry,
            applied_spec=desired,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )


class EMUSCIMUserProvider(BaseProvider):
    """
    Manages GHEC EMU SCIM Users (Lifecycle, Provisioning, Enterprise Role Assignments).
    SCIM: /scim/v2/enterprises/{enterprise}/Users
    """

    def read(self, manifest: GitHubManifest) -> Optional[ResourceState]:
        username = manifest.spec.get("userName") or manifest.metadata.name
        try:
            res = self.client.scim_request(
                "GET",
                "/Users",
                params={"filter": f'userName eq "{username}"'},
            )
            resources = res.get("Resources", []) if isinstance(res, dict) else []
            if not resources:
                return None
            user = resources[0]
            return ResourceState(
                resource_id=manifest.resource_id,
                kind=manifest.kind,
                numeric_id=user.get("id"),
                attributes={
                    "userName": user.get("userName"),
                    "name": user.get("name", {}),
                    "emails": user.get("emails", []),
                    "roles": user.get("roles", []),
                    "active": user.get("active", True),
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
                "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
                "userName": desired.get("userName", manifest.metadata.name),
                "name": desired.get("name", {}),
                "emails": desired.get("emails", []),
                "roles": desired.get("roles", []),
                "active": desired.get("active", True),
            }
            res = self.client.scim_request("POST", "/Users", json_data=payload)
            user_id = res.get("id") if isinstance(res, dict) else None
        elif plan.action == ActionType.UPDATE and plan.current_state:
            user_id = plan.current_state.get("numeric_id")
            payload = {
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [
                    {
                        "op": "replace",
                        "path": "active",
                        "value": desired.get("active", True),
                    }
                ],
            }
            self.client.scim_request("PATCH", f"/Users/{user_id}", json_data=payload)
        else:
            user_id = None

        return ResourceState(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            numeric_id=user_id,
            attributes=desired,
            applied_spec=desired,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )


class EnterpriseCustomRoleProvider(BaseProvider):
    """
    Manages Enterprise-wide custom roles applying across all organizations.
    REST: /enterprises/{enterprise}/custom-roles
    """

    def read(self, manifest: GitHubManifest) -> Optional[ResourceState]:
        ent = manifest.metadata.enterprise or manifest.metadata.name
        role_name = manifest.metadata.name
        try:
            data = self.client.rest("GET", f"/enterprises/{ent}/custom-roles")
            roles = data.get("custom_roles", []) if isinstance(data, dict) else []
            for r in roles:
                if r.get("name") == role_name:
                    return ResourceState(
                        resource_id=manifest.resource_id,
                        kind=manifest.kind,
                        numeric_id=r.get("id"),
                        attributes={
                            "name": r.get("name"),
                            "description": r.get("description"),
                            "base_role": r.get("base_role"),
                            "permissions": r.get("permissions", []),
                        },
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
        for key in ["description", "base_role", "permissions"]:
            if key in desired and current.attributes.get(key) != desired[key]:
                diff[key] = {"old": current.attributes.get(key), "new": desired[key]}

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
        ent = manifest.metadata.enterprise or manifest.metadata.name
        desired = manifest.spec

        payload = {
            "name": manifest.metadata.name,
            "description": desired.get("description", ""),
            "base_role": desired.get("base_role", "read"),
            "permissions": desired.get("permissions", []),
        }

        if plan.action == ActionType.CREATE:
            res = self.client.rest("POST", f"/enterprises/{ent}/custom-roles", json_data=payload)
            role_id = res.get("id") if isinstance(res, dict) else None
        elif plan.action == ActionType.UPDATE:
            role_id = plan.current_state.get("numeric_id") if plan.current_state else None
            if not role_id:
                curr = self.read(manifest)
                role_id = curr.numeric_id if curr else None

            if role_id:
                res = self.client.rest("PATCH", f"/enterprises/{ent}/custom-roles/{role_id}", json_data=payload)
        else:
            role_id = None

        return ResourceState(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            numeric_id=role_id,
            attributes=payload,
            applied_spec=desired,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )


class EnterpriseRunnerGroupProvider(BaseProvider):
    """
    Manages Enterprise Actions Self-Hosted Runner Groups and access policies.
    REST: /enterprises/{enterprise}/actions/runner-groups
    """

    def read(self, manifest: GitHubManifest) -> Optional[ResourceState]:
        ent = manifest.metadata.enterprise or manifest.metadata.name
        group_name = manifest.metadata.name
        try:
            data = self.client.rest("GET", f"/enterprises/{ent}/actions/runner-groups")
            groups = data.get("runner_groups", []) if isinstance(data, dict) else []
            for g in groups:
                if g.get("name") == group_name:
                    return ResourceState(
                        resource_id=manifest.resource_id,
                        kind=manifest.kind,
                        numeric_id=g.get("id"),
                        attributes={
                            "name": g.get("name"),
                            "visibility": g.get("visibility"),
                            "selected_organization_ids": g.get("selected_organization_ids", []),
                            "allows_public_repositories": g.get("allows_public_repositories", False),
                        },
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
        for k in ["visibility", "selected_organization_ids", "allows_public_repositories"]:
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
        ent = manifest.metadata.enterprise or manifest.metadata.name
        desired = manifest.spec

        payload = {
            "name": manifest.metadata.name,
            "visibility": desired.get("visibility", "all"),
            "selected_organization_ids": desired.get("selected_organization_ids", []),
            "allows_public_repositories": desired.get("allows_public_repositories", False),
        }

        if plan.action == ActionType.CREATE:
            res = self.client.rest("POST", f"/enterprises/{ent}/actions/runner-groups", json_data=payload)
            group_id = res.get("id") if isinstance(res, dict) else None
        elif plan.action == ActionType.UPDATE:
            group_id = plan.current_state.get("numeric_id") if plan.current_state else None
            if not group_id:
                curr = self.read(manifest)
                group_id = curr.numeric_id if curr else None

            if group_id:
                self.client.rest("PATCH", f"/enterprises/{ent}/actions/runner-groups/{group_id}", json_data=payload)
        else:
            group_id = None

        return ResourceState(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            numeric_id=group_id,
            attributes=payload,
            applied_spec=desired,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )


class GitHubAppProvider(BaseProvider):
    """
    Manages GitHub Apps at the Organization or Enterprise scope.
    Enterprise: /enterprises/{enterprise}/apps
    Organization: /orgs/{organization}/apps
    """

    def _get_base_path(self, manifest: GitHubManifest) -> str:
        if manifest.metadata.organization:
            return f"/orgs/{manifest.metadata.organization}/apps"
        ent = manifest.metadata.enterprise or manifest.metadata.name
        return f"/enterprises/{ent}/apps"

    def read(self, manifest: GitHubManifest) -> Optional[ResourceState]:
        base_path = self._get_base_path(manifest)
        app_name = manifest.metadata.name
        try:
            apps = self.client.rest("GET", base_path)
            if not isinstance(apps, list):
                return None
            for a in apps:
                if a.get("name") == app_name or a.get("slug") == app_name:
                    return ResourceState(
                        resource_id=manifest.resource_id,
                        kind=manifest.kind,
                        node_id=a.get("node_id"),
                        numeric_id=a.get("id"),
                        attributes={
                            "name": a.get("name"),
                            "slug": a.get("slug"),
                            "client_id": a.get("client_id"),
                            "description": a.get("description"),
                            "url": a.get("url"),
                            "permissions": a.get("permissions", {}),
                            "events": a.get("events", []),
                        },
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
        for k in ["description", "url", "default_permissions", "default_events"]:
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
        import os
        from pathlib import Path

        base_path = self._get_base_path(manifest)
        desired = manifest.spec

        payload = {
            "name": manifest.metadata.name,
            "url": desired.get("url", "https://github.com"),
            "description": desired.get("description", ""),
            "default_permissions": desired.get("default_permissions", {}),
            "default_events": desired.get("default_events", []),
            "public": desired.get("public", False),
        }
        if "hook_attributes" in desired:
            payload["hook_attributes"] = desired["hook_attributes"]

        if plan.action == ActionType.CREATE:
            res = self.client.rest("POST", base_path, json_data=payload)
            app_id = res.get("id") if isinstance(res, dict) else None
            node_id = res.get("node_id") if isinstance(res, dict) else None
            slug = res.get("slug", manifest.metadata.name)
            client_id = res.get("client_id")
            pem_content = res.get("pem")

            # Handle credential output
            output_config = desired.get("output_credentials", {})
            pem_file = output_config.get("private_key_file")
            if pem_file and pem_content:
                out_path = Path(pem_file)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(pem_content, encoding="utf-8")
                try:
                    os.chmod(out_path, 0o600)
                except OSError:
                    pass

        elif plan.action == ActionType.UPDATE and plan.current_state:
            app_id = plan.current_state.get("numeric_id")
            node_id = plan.current_state.get("node_id")
            slug = plan.current_state.get("slug", manifest.metadata.name)
            client_id = plan.current_state.get("client_id")
            if app_id:
                self.client.rest("PATCH", f"/apps/{app_id}", json_data=payload)
        else:
            app_id = None
            node_id = None
            slug = manifest.metadata.name
            client_id = None

        return ResourceState(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            node_id=node_id,
            numeric_id=app_id,
            attributes={
                "name": manifest.metadata.name,
                "slug": slug,
                "client_id": client_id,
                "client_secret": "******",
                "pem": "******",
                "url": desired.get("url"),
                "description": desired.get("description"),
            },
            applied_spec=desired,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )



