"""Organization and Team construct providers."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from gh_iac.core.manifest import GitHubManifest
from gh_iac.core.state import ResourceState
from gh_iac.providers.base import ActionType, BaseProvider, ResourcePlan


class OrganizationProvider(BaseProvider):
    """
    Manages GitHub Organizations.
    Uses GraphQL Organization query/mutations for attributes and REST for org administration.
    """

    def read(self, manifest: GitHubManifest) -> Optional[ResourceState]:
        org_login = manifest.metadata.name
        query = """
        query GetOrg($login: String!) {
          organization(login: $login) {
            id
            login
            name
            description
            email
            websiteUrl
            requiresTwoFactorAuthentication
            membersCanCreateRepositories
          }
        }
        """
        try:
            data = self.client.graphql(query, {"login": org_login})
            org = data.get("organization")
            if not org:
                return None
            return ResourceState(
                resource_id=manifest.resource_id,
                kind=manifest.kind,
                node_id=org.get("id"),
                attributes=org,
                applied_spec=manifest.spec,
                last_updated=datetime.now(timezone.utc).isoformat(),
            )
        except Exception:
            return None

    def plan(self, manifest: GitHubManifest, current: Optional[ResourceState]) -> ResourcePlan:
        desired = manifest.spec
        if not current:
            # Creation of orgs usually occurs via enterprise admin endpoint or already exists
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
        org_login = manifest.metadata.name
        desired = manifest.spec

        # If enterprise is specified and action is CREATE, provision org under enterprise via REST
        if plan.action == ActionType.CREATE and manifest.metadata.enterprise:
            payload = {
                "login": org_login,
                "admin": desired.get("admin", "admin"),
            }
            # REST: POST /enterprises/{enterprise}/orgs
            self.client.rest(
                "POST", f"/enterprises/{manifest.metadata.enterprise}/orgs", json_data=payload
            )

        # Update org attributes (PATCH /orgs/{org})
        self.client.rest("PATCH", f"/orgs/{org_login}", json_data=desired)

        return ResourceState(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            attributes=desired,
            applied_spec=desired,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )


class TeamProvider(BaseProvider):
    """
    Manages GitHub Teams.
    Uses GraphQL team queries and team mutations where supported, with REST team API fallback.
    """

    def read(self, manifest: GitHubManifest) -> Optional[ResourceState]:
        org = manifest.metadata.organization
        team_slug = manifest.metadata.name
        if not org:
            raise ValueError("Team construct requires metadata.organization.")

        query = """
        query GetTeam($org: String!, $slug: String!) {
          organization(login: $org) {
            team(slug: $slug) {
              id
              name
              slug
              description
              privacy
            }
          }
        }
        """
        try:
            data = self.client.graphql(query, {"org": org, "slug": team_slug})
            org_data = data.get("organization") or {}
            team = org_data.get("team")
            if not team:
                return None
            return ResourceState(
                resource_id=manifest.resource_id,
                kind=manifest.kind,
                node_id=team.get("id"),
                attributes=team,
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
        for k in ["name", "description", "privacy"]:
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
        team_slug = manifest.metadata.name
        desired = manifest.spec

        if plan.action == ActionType.CREATE:
            # REST: POST /orgs/{org}/teams
            payload = {
                "name": desired.get("name", team_slug),
                "description": desired.get("description", ""),
                "privacy": desired.get("privacy", "closed").lower(),
            }
            res = self.client.rest("POST", f"/orgs/{org}/teams", json_data=payload)
            node_id = res.get("node_id") if isinstance(res, dict) else None
        elif plan.action == ActionType.UPDATE:
            payload = {
                "name": desired.get("name", team_slug),
                "description": desired.get("description", ""),
                "privacy": desired.get("privacy", "closed").lower(),
            }
            res = self.client.rest("PATCH", f"/orgs/{org}/teams/{team_slug}", json_data=payload)
            node_id = res.get("node_id") if isinstance(res, dict) else None
        else:
            node_id = None

        return ResourceState(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            node_id=node_id,
            attributes=desired,
            applied_spec=desired,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )


class OrganizationSecretProvider(BaseProvider):
    """
    Manages GitHub Organization Actions secrets with client-side Libsodium encryption.
    REST: /orgs/{org}/actions/secrets/{secret_name}
    """

    def read(self, manifest: GitHubManifest) -> Optional[ResourceState]:
        org = manifest.metadata.organization
        secret_name = manifest.metadata.name
        try:
            sec_info = self.client.rest("GET", f"/orgs/{org}/actions/secrets/{secret_name}")
            if not isinstance(sec_info, dict):
                return None
            return ResourceState(
                resource_id=manifest.resource_id,
                kind=manifest.kind,
                attributes={
                    "name": sec_info.get("name"),
                    "visibility": sec_info.get("visibility"),
                    "created_at": sec_info.get("created_at"),
                    "updated_at": sec_info.get("updated_at"),
                },
                applied_spec={"visibility": sec_info.get("visibility")},
                last_updated=datetime.now(timezone.utc).isoformat(),
            )
        except Exception:
            return None

    def plan(self, manifest: GitHubManifest, current: Optional[ResourceState]) -> ResourcePlan:
        desired = manifest.spec
        desired_state = {"visibility": desired.get("visibility", "all"), "value": "******"}
        if "selected_repository_ids" in desired:
            desired_state["selected_repository_ids"] = desired["selected_repository_ids"]

        if not current:
            return ResourcePlan(
                resource_id=manifest.resource_id,
                kind=manifest.kind,
                action=ActionType.CREATE,
                diff={"desired": desired_state},
                current_state=None,
                desired_state=desired_state,
            )

        diff: Dict[str, Any] = {}
        if (
            "visibility" in desired
            and current.attributes.get("visibility") != desired["visibility"]
        ):
            diff["visibility"] = {
                "old": current.attributes.get("visibility"),
                "new": desired["visibility"],
            }

        if (
            "selected_repository_ids" in desired
            and current.attributes.get("selected_repository_ids")
            != desired["selected_repository_ids"]
        ):
            diff["selected_repository_ids"] = {
                "old": current.attributes.get("selected_repository_ids"),
                "new": desired["selected_repository_ids"],
            }

        # Secrets are always re-applied on update
        diff["value"] = {"old": "******", "new": "******"}
        return ResourcePlan(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            action=ActionType.UPDATE,
            diff=diff,
            current_state=current.attributes,
            desired_state=desired_state,
        )

    def apply(self, plan: ResourcePlan, manifest: GitHubManifest) -> ResourceState:
        from gh_iac.core.credentials import CredentialResolver, encrypt_github_secret

        org = manifest.metadata.organization
        secret_name = manifest.metadata.name
        desired = manifest.spec

        # 1. Resolve raw secret value safely
        resolver = CredentialResolver()
        raw_secret = resolver.resolve(desired.get("value", ""))

        # 2. Get Organization Actions public key
        key_data = self.client.rest("GET", f"/orgs/{org}/actions/secrets/public-key")
        public_key_b64 = key_data["key"]
        key_id = key_data["key_id"]

        # 3. Libsodium sealed box encryption
        encrypted_val = encrypt_github_secret(public_key_b64, raw_secret)

        # 4. PUT secret
        payload = {
            "encrypted_value": encrypted_val,
            "key_id": key_id,
            "visibility": desired.get("visibility", "all"),
        }
        if "selected_repository_ids" in desired:
            payload["selected_repository_ids"] = desired["selected_repository_ids"]

        self.client.rest("PUT", f"/orgs/{org}/actions/secrets/{secret_name}", json_data=payload)

        attributes = {
            "name": secret_name,
            "visibility": desired.get("visibility", "all"),
            "value": "******",
        }
        if "selected_repository_ids" in desired:
            attributes["selected_repository_ids"] = desired["selected_repository_ids"]

        return ResourceState(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            attributes=attributes,
            applied_spec=attributes,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )


class OrganizationRulesetProvider(BaseProvider):
    """
    Manages organization-wide repository rulesets applied across repos.
    REST: /orgs/{org}/rulesets
    """

    def read(self, manifest: GitHubManifest) -> Optional[ResourceState]:
        org = manifest.metadata.organization or manifest.metadata.name
        ruleset_name = manifest.spec.get("name", manifest.metadata.name)

        try:
            rulesets = self.client.rest("GET", f"/orgs/{org}/rulesets")
            if isinstance(rulesets, list):
                for rs in rulesets:
                    if rs.get("name") == ruleset_name:
                        detail = self.client.rest("GET", f"/orgs/{org}/rulesets/{rs.get('id')}")
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
        for k in ["enforcement", "target", "rules", "conditions"]:
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
        org = manifest.metadata.organization or manifest.metadata.name
        desired = manifest.spec

        numeric_id = None
        if plan.action == ActionType.CREATE:
            res = self.client.rest("POST", f"/orgs/{org}/rulesets", json_data=desired)
            numeric_id = res.get("id") if isinstance(res, dict) else None
        elif plan.action == ActionType.UPDATE:
            ruleset_id = plan.current_state.get("numeric_id") if plan.current_state else None
            if not ruleset_id:
                curr = self.read(manifest)
                ruleset_id = curr.numeric_id if curr else None

            if ruleset_id:
                res = self.client.rest(
                    "PUT", f"/orgs/{org}/rulesets/{ruleset_id}", json_data=desired
                )
                numeric_id = ruleset_id

        return ResourceState(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            numeric_id=numeric_id,
            attributes=desired,
            applied_spec=desired,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )


class OrganizationVariableProvider(BaseProvider):
    """
    Manages GitHub Organization Actions configuration variables.
    REST: /orgs/{org}/actions/variables
    """

    def read(self, manifest: GitHubManifest) -> Optional[ResourceState]:
        org = manifest.metadata.organization
        var_name = manifest.metadata.name
        try:
            var_data = self.client.rest("GET", f"/orgs/{org}/actions/variables/{var_name}")
            if not isinstance(var_data, dict):
                return None
            return ResourceState(
                resource_id=manifest.resource_id,
                kind=manifest.kind,
                attributes={
                    "name": var_data.get("name"),
                    "value": var_data.get("value"),
                    "visibility": var_data.get("visibility"),
                    "created_at": var_data.get("created_at"),
                    "updated_at": var_data.get("updated_at"),
                },
                applied_spec={
                    "value": var_data.get("value"),
                    "visibility": var_data.get("visibility"),
                },
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
        for k in ["value", "visibility"]:
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
        var_name = manifest.metadata.name
        desired = manifest.spec

        payload = {
            "name": var_name,
            "value": desired.get("value", ""),
            "visibility": desired.get("visibility", "all"),
        }
        if "selected_repository_ids" in desired:
            payload["selected_repository_ids"] = desired["selected_repository_ids"]

        if plan.action == ActionType.CREATE:
            self.client.rest("POST", f"/orgs/{org}/actions/variables", json_data=payload)
        elif plan.action == ActionType.UPDATE:
            self.client.rest(
                "PATCH", f"/orgs/{org}/actions/variables/{var_name}", json_data=payload
            )

        return ResourceState(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            attributes=payload,
            applied_spec=desired,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )


class OrganizationWebhookProvider(BaseProvider):
    """
    Manages Organization event webhooks.
    REST: /orgs/{org}/hooks
    """

    def read(self, manifest: GitHubManifest) -> Optional[ResourceState]:
        org = manifest.metadata.organization
        target_url = manifest.spec.get("config", {}).get("url")
        hook_name = manifest.metadata.name

        try:
            hooks = self.client.rest("GET", f"/orgs/{org}/hooks")
            if isinstance(hooks, list):
                for h in hooks:
                    config = h.get("config", {})
                    if config.get("url") == target_url or h.get("name") == hook_name:
                        return ResourceState(
                            resource_id=manifest.resource_id,
                            kind=manifest.kind,
                            numeric_id=h.get("id"),
                            attributes=h,
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
        for k in ["events", "active"]:
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
        desired = manifest.spec

        payload = {
            "name": desired.get("name", "web"),
            "config": desired.get("config", {}),
            "events": desired.get("events", ["push"]),
            "active": desired.get("active", True),
        }

        numeric_id = None
        if plan.action == ActionType.CREATE:
            res = self.client.rest("POST", f"/orgs/{org}/hooks", json_data=payload)
            numeric_id = res.get("id") if isinstance(res, dict) else None
        elif plan.action == ActionType.UPDATE:
            hook_id = plan.current_state.get("numeric_id") if plan.current_state else None
            if not hook_id:
                curr = self.read(manifest)
                hook_id = curr.numeric_id if curr else None

            if hook_id:
                res = self.client.rest("PATCH", f"/orgs/{org}/hooks/{hook_id}", json_data=payload)
                numeric_id = hook_id

        return ResourceState(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            numeric_id=numeric_id,
            attributes=payload,
            applied_spec=desired,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )


class OrganizationRunnerGroupProvider(BaseProvider):
    """
    Manages organization Actions self-hosted runner groups.
    REST: /orgs/{org}/actions/runner-groups
    """

    def read(self, manifest: GitHubManifest) -> Optional[ResourceState]:
        org = manifest.metadata.organization
        group_name = manifest.metadata.name

        try:
            data = self.client.rest("GET", f"/orgs/{org}/actions/runner-groups")
            groups = data.get("runner_groups", []) if isinstance(data, dict) else []
            for g in groups:
                if g.get("name") == group_name:
                    return ResourceState(
                        resource_id=manifest.resource_id,
                        kind=manifest.kind,
                        numeric_id=g.get("id"),
                        attributes=g,
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
        for k in ["visibility", "allows_public_repositories", "selected_repository_ids"]:
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
        group_name = manifest.metadata.name
        desired = manifest.spec

        payload = {
            "name": group_name,
            "visibility": desired.get("visibility", "all"),
            "allows_public_repositories": desired.get("allows_public_repositories", False),
        }
        if "selected_repository_ids" in desired:
            payload["selected_repository_ids"] = desired["selected_repository_ids"]

        numeric_id = None
        if plan.action == ActionType.CREATE:
            res = self.client.rest("POST", f"/orgs/{org}/actions/runner-groups", json_data=payload)
            numeric_id = res.get("id") if isinstance(res, dict) else None
        elif plan.action == ActionType.UPDATE:
            group_id = plan.current_state.get("numeric_id") if plan.current_state else None
            if not group_id:
                curr = self.read(manifest)
                group_id = curr.numeric_id if curr else None

            if group_id:
                res = self.client.rest(
                    "PATCH", f"/orgs/{org}/actions/runner-groups/{group_id}", json_data=payload
                )
                numeric_id = group_id

        return ResourceState(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            numeric_id=numeric_id,
            attributes=payload,
            applied_spec=desired,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )
