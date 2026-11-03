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
            self.client.rest("POST", f"/enterprises/{manifest.metadata.enterprise}/orgs", json_data=payload)

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
        if not current:
            return ResourcePlan(
                resource_id=manifest.resource_id,
                kind=manifest.kind,
                action=ActionType.CREATE,
                diff={"desired": {"visibility": desired.get("visibility", "all"), "value": "******"}},
                current_state=None,
                desired_state={"visibility": desired.get("visibility", "all"), "value": "******"},
            )

        diff: Dict[str, Any] = {}
        if "visibility" in desired and current.attributes.get("visibility") != desired["visibility"]:
            diff["visibility"] = {"old": current.attributes.get("visibility"), "new": desired["visibility"]}

        # Secrets are always re-applied on update
        diff["value"] = {"old": "******", "new": "******"}
        return ResourcePlan(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            action=ActionType.UPDATE,
            diff=diff,
            current_state=current.attributes,
            desired_state={"visibility": desired.get("visibility", "all"), "value": "******"},
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
        self.client.rest("PUT", f"/orgs/{org}/actions/secrets/{secret_name}", json_data=payload)

        return ResourceState(
            resource_id=manifest.resource_id,
            kind=manifest.kind,
            attributes={
                "name": secret_name,
                "visibility": desired.get("visibility", "all"),
                "value": "******",
            },
            applied_spec={"visibility": desired.get("visibility", "all"), "value": "******"},
            last_updated=datetime.now(timezone.utc).isoformat(),
        )

