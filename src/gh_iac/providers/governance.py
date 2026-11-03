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
            res = self.client.rest(
                "POST", f"/orgs/{org}/custom-repository-roles", json_data=payload
            )
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
            settings = self.client.rest(
                "GET", f"/enterprises/{enterprise}/settings/security_analysis"
            )
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


class EnterpriseSecurityConfigurationProvider(BaseProvider):
    """
    Manages Enterprise Code Security Configurations for Repositories.
    Enables declarative creation of GHAS profiles (Advanced Security, Secret Scanning,
    Push Protection, CodeQL, Dependabot, Private Vulnerability Reporting),
    enforcement locks preventing repo admin overrides, setting enterprise defaults,
    and attaching configurations directly to repositories.
    REST: /enterprises/{enterprise}/code-security/configurations
    """

    def read(self, manifest: GitHubManifest) -> Optional[ResourceState]:
        enterprise = manifest.metadata.enterprise or manifest.metadata.name
        config_name = manifest.spec.get("name", manifest.metadata.name)
        try:
            configs = self.client.rest(
                "GET", f"/enterprises/{enterprise}/code-security/configurations"
            )
            if not isinstance(configs, list):
                return None
            for c in configs:
                if c.get("name") == config_name:
                    return ResourceState(
                        resource_id=manifest.resource_id,
                        kind=manifest.kind,
                        numeric_id=c.get("id"),
                        attributes=c,
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
        enterprise = manifest.metadata.enterprise or manifest.metadata.name
        desired = manifest.spec
        numeric_id = None

        default_for_new_repos = desired.get("default_for_new_repos")
        selected_repositories = desired.get("repositories")

        config_keys = [
            "name",
            "description",
            "advanced_security",
            "dependency_graph",
            "dependabot_alerts",
            "dependabot_security_updates",
            "code_scanning_default_setup",
            "secret_scanning",
            "secret_scanning_push_protection",
            "secret_scanning_validity_checks",
            "private_vulnerability_reporting",
            "enforcement",
        ]
        config_payload = {k: desired[k] for k in config_keys if k in desired}
        if "name" not in config_payload:
            config_payload["name"] = manifest.metadata.name

        if plan.action == ActionType.CREATE:
            res = self.client.rest(
                "POST",
                f"/enterprises/{enterprise}/code-security/configurations",
                json_data=config_payload,
            )
            numeric_id = res.get("id") if isinstance(res, dict) else None
        elif plan.action == ActionType.UPDATE:
            numeric_id = plan.current_state.get("numeric_id") if plan.current_state else None
            if not numeric_id:
                curr = self.read(manifest)
                numeric_id = curr.numeric_id if curr else None
            if numeric_id:
                res = self.client.rest(
                    "PATCH",
                    f"/enterprises/{enterprise}/code-security/configurations/{numeric_id}",
                    json_data=config_payload,
                )

        if numeric_id and default_for_new_repos:
            try:
                self.client.rest(
                    "PUT",
                    f"/enterprises/{enterprise}/code-security/configurations/{numeric_id}/defaults",
                    json_data={"default_for_new_repos": default_for_new_repos},
                )
            except Exception:
                pass

        if numeric_id and selected_repositories:
            try:
                self.client.rest(
                    "POST",
                    f"/enterprises/{enterprise}/code-security/configurations/{numeric_id}/repositories",
                    json_data={"selected_repository_ids": selected_repositories},
                )
            except Exception:
                pass

        return ResourceState(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            numeric_id=numeric_id,
            attributes=desired,
            applied_spec=desired,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )
