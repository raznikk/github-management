"""Unit tests for Dependency Graph (DAG) and topological concurrency execution."""

import pytest
from gh_iac.core.dag import CyclicDependencyError, DependencyGraph
from gh_iac.core.manifest import GitHubManifest, ManifestMetadata


def test_dag_hierarchical_tiering():
    m_ent = GitHubManifest(
        kind="EnterprisePolicy",
        metadata=ManifestMetadata(name="ent-pol", enterprise="octo"),
        spec={},
    )
    m_org = GitHubManifest(
        kind="Organization",
        metadata=ManifestMetadata(name="cloud-org", enterprise="octo"),
        spec={},
    )
    m_repo = GitHubManifest(
        kind="Repository",
        metadata=ManifestMetadata(name="app-repo", organization="cloud-org"),
        spec={},
    )
    m_ruleset = GitHubManifest(
        kind="RepositoryRuleset",
        metadata=ManifestMetadata(
            name="main-rules", organization="cloud-org", repository="app-repo"
        ),
        spec={},
    )

    dag = DependencyGraph([m_ruleset, m_repo, m_org, m_ent])
    tiers = dag.get_execution_tiers()

    # Tiers must be ordered: Enterprise -> Org -> Repo -> Ruleset
    assert len(tiers) == 4
    assert tiers[0][0].kind == "EnterprisePolicy"
    assert tiers[1][0].kind == "Organization"
    assert tiers[2][0].kind == "Repository"
    assert tiers[3][0].kind == "RepositoryRuleset"


def test_dag_parallel_resources_in_same_tier():
    m_org = GitHubManifest(
        kind="Organization",
        metadata=ManifestMetadata(name="cloud-org"),
        spec={},
    )
    # Two independent repositories in the same org
    m_repo1 = GitHubManifest(
        kind="Repository",
        metadata=ManifestMetadata(name="repo-1", organization="cloud-org"),
        spec={},
    )
    m_repo2 = GitHubManifest(
        kind="Repository",
        metadata=ManifestMetadata(name="repo-2", organization="cloud-org"),
        spec={},
    )

    dag = DependencyGraph([m_repo1, m_repo2, m_org])
    tiers = dag.get_execution_tiers()

    assert len(tiers) == 2
    assert tiers[0][0].kind == "Organization"
    tier1_names = {m.metadata.name for m in tiers[1]}
    assert tier1_names == {"repo-1", "repo-2"}


def test_dag_cycle_detection_raises():
    m1 = GitHubManifest(
        kind="Repository",
        metadata=ManifestMetadata(name="repo-a", labels={"depends_on": "Repository/repo-b"}),
        spec={},
    )
    m2 = GitHubManifest(
        kind="Repository",
        metadata=ManifestMetadata(name="repo-b", labels={"depends_on": "Repository/repo-a"}),
        spec={},
    )

    dag = DependencyGraph([m1, m2])
    with pytest.raises(CyclicDependencyError):
        dag.get_execution_tiers()
