"""Governance and Security Providers (Custom Repository Roles, GHAS & Secret Scanning)."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from gh_iac.core.manifest import GitHubManifest
from gh_iac.core.state import ResourceState
from gh_iac.providers.base import ActionType, BaseProvider, ResourcePlan


class CustomRepositoryRoleProvider(BaseProvider):
    """
    Manages custom repository roles at the Organization or Enterprise level.
    GitHub provides custom role APIs via REST endpoint /orgs/{org}/custom-repository-roles
    or enterprise custom roles endpoints.
    """

    def read(self, manifest: GitHubManifest) -> Optional[ResourceState]:
        org = manifest.metadata.organization
        role_name = manifest.metadata.name

        if not org:
            raise ValueError("CustomRepositoryRole requires metadata.organization.")

        try:
            # REST: GET /orgs/{org}/custom-repository-roles
            data = self.client.rest("GET", f"/orgs/{org}/custom-repository-roles")
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
        org = manifest.metadata.organization
        desired = manifest.spec

        payload = {
            "name": manifest.metadata.name,
            "description": desired.get("description", ""),
            "base_role": desired.get("base_role", "read"),
            "permissions": desired.get("permissions", []),
        }

        if plan.action == ActionType.CREATE:
            res = self.client.rest("POST", f"/orgs/{org}/custom-repository-roles", json_data=payload)
            role_id = res.get("id") if isinstance(res, dict) else None
        elif plan.action == ActionType.UPDATE:
            role_id = plan.current_state.get("numeric_id") if plan.current_state else None
            if not role_id and manifest.resource_id:
                # Re-read to acquire ID
                current = self.read(manifest)
                role_id = current.numeric_id if current else None

            if role_id:
                res = self.client.rest(
                    "PATCH",
                    f"/orgs/{org}/custom-repository-roles/{role_id}",
                    json_data=payload,
                )
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


class EnterpriseSecuritySettingProvider(BaseProvider):
    """
    Manages Enterprise-wide Security & Governance:
    - Advanced Security (GHAS) licensing
    - Secret scanning & push protection
    - Dependabot & Code scanning default configurations
    Prefers GraphQL enterprise queries where available, backed by REST security management APIs.
    """

    def read(self, manifest: GitHubManifest) -> Optional[ResourceState]:
        enterprise = manifest.metadata.enterprise or manifest.metadata.name
        try:
            # Query enterprise security status via REST
            settings = self.client.rest("GET", f"/enterprises/{enterprise}/settings/security_analysis")
            return ResourceState(
                resource_id=manifest.resource_id,
                kind=manifest.kind,
                attributes=settings if isinstance(settings, dict) else {},
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
        enterprise = manifest.metadata.enterprise or manifest.metadata.name
        desired = manifest.spec

        # Apply security analysis configuration: advanced_security, secret_scanning, etc.
        self.client.rest(
            "PATCH",
            f"/enterprises/{enterprise}/settings/security_analysis",
            json_data=desired,
        )

        return ResourceState(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            attributes=desired,
            applied_spec=desired,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )
