"""Unit tests for State Backends, Locking, and AES-GCM Encryption at rest."""

from pathlib import Path

import pytest
import respx

from gh_iac.core.state import (
    LocalStateBackend,
    ResourceState,
    StateFile,
    StateLockError,
)


def test_plain_state_backend_roundtrip(tmp_path: Path):
    state_file = tmp_path / "state.json"
    backend = LocalStateBackend(state_path=state_file)

    res = ResourceState(
        resource_id="Repository/octo/core-app",
        kind="Repository",
        node_id="REPO_1",
        attributes={"name": "core-app"},
    )
    state = StateFile(environment="ghec", resources={res.resource_id: res})
    backend.write_state(state)

    loaded = backend.read_state()
    assert loaded.environment == "ghec"
    assert "Repository/octo/core-app" in loaded.resources
    assert loaded.resources["Repository/octo/core-app"].node_id == "REPO_1"


def test_encrypted_state_backend_aes_gcm(tmp_path: Path):
    state_file = tmp_path / "encrypted_state.bin"
    passphrase = "my-super-strong-encryption-passphrase-123"

    backend = LocalStateBackend(state_path=state_file, passphrase=passphrase)
    res = ResourceState(
        resource_id="Repository/octo/sensitive-app",
        kind="Repository",
        attributes={"name": "sensitive-app"},
    )
    state = StateFile(environment="ghec", resources={res.resource_id: res})
    backend.write_state(state)

    # 1. Verify file on disk is encrypted (raw ciphertext, not JSON)
    raw_content = state_file.read_bytes()
    assert b"sensitive-app" not in raw_content
    assert b"Repository/octo" not in raw_content

    # 2. Read with correct passphrase succeeds
    loaded = backend.read_state()
    assert loaded.resources["Repository/octo/sensitive-app"].attributes["name"] == "sensitive-app"

    # 3. Read with wrong passphrase fails
    wrong_backend = LocalStateBackend(state_path=state_file, passphrase="wrong-passphrase")
    with pytest.raises(ValueError):
        wrong_backend.read_state()


def test_state_locking(tmp_path: Path):
    state_file = tmp_path / "state.json"
    backend1 = LocalStateBackend(state_path=state_file)
    backend2 = LocalStateBackend(state_path=state_file)

    # Acquire lock
    backend1.lock()
    assert backend1.is_locked()

    # Second lock attempt raises StateLockError
    with pytest.raises(StateLockError):
        backend2.lock()

    # Release lock
    backend1.unlock()
    assert not backend1.is_locked()

    # Second can now lock
    backend2.lock()
    assert backend2.is_locked()
    backend2.unlock()


@respx.mock
def test_http_remote_backend():
    from gh_iac.core.state import HttpRemoteBackend

    address = "https://state-server.internal/v1/states/ghec"
    backend = HttpRemoteBackend(address=address)

    # 1. 404 on initial read returns empty state
    respx.get(address).mock(return_value=respx.MockResponse(404))
    state = backend.read_state()
    assert state.environment == "default"

    # 2. Write state
    put_route = respx.put(address).mock(return_value=respx.MockResponse(200))
    res = ResourceState(resource_id="Repo/1", kind="Repository", attributes={"name": "foo"})
    state.resources[res.resource_id] = res
    backend.write_state(state)
    assert put_route.called

    # 3. Read state returns updated
    respx.get(address).mock(
        return_value=respx.MockResponse(
            200,
            json=state.model_dump(),
        )
    )
    loaded = backend.read_state()
    assert "Repo/1" in loaded.resources

    # 4. Lock acquisition and conflict
    lock_route = respx.post(f"{address}/lock").mock(return_value=respx.MockResponse(200))
    backend.lock()
    assert lock_route.called

    # Conflicting lock
    respx.post(f"{address}/lock").mock(return_value=respx.MockResponse(423))
    with pytest.raises(StateLockError):
        backend.lock()

    # Unlock
    unlock_route = respx.delete(f"{address}/lock").mock(return_value=respx.MockResponse(200))
    backend.unlock()
    assert unlock_route.called


@respx.mock
def test_s3_state_backend():
    from gh_iac.core.state import S3StateBackend

    backend = S3StateBackend(bucket="my-corp-iac", key="ghec/state.json", region="us-west-2")
    base_url = "https://my-corp-iac.s3.us-west-2.amazonaws.com/ghec/state.json"
    lock_url = f"{base_url}.lock"

    # 1. 404 returns empty state
    respx.get(base_url).mock(return_value=respx.MockResponse(404))
    state = backend.read_state()
    assert state.environment == "default"

    # 2. Write state
    put_route = respx.put(base_url).mock(return_value=respx.MockResponse(200))
    backend.write_state(state)
    assert put_route.called

    # 3. Lock & unlock
    respx.get(lock_url).mock(return_value=respx.MockResponse(404))
    assert not backend.is_locked()

    respx.put(lock_url).mock(return_value=respx.MockResponse(200))
    backend.lock()

    # When lock exists, locking raises StateLockError
    respx.get(lock_url).mock(return_value=respx.MockResponse(200))
    assert backend.is_locked()
    with pytest.raises(StateLockError):
        backend.lock()

    del_route = respx.delete(lock_url).mock(return_value=respx.MockResponse(204))
    backend.unlock()
    assert del_route.called


@respx.mock
def test_gcs_and_azure_backends():
    from gh_iac.core.state import AzureBlobStateBackend, GCSStateBackend

    # GCS
    gcs = GCSStateBackend(bucket="my-gcs-bucket", blob_name="iac/state.json")
    respx.get("https://storage.googleapis.com/my-gcs-bucket/iac/state.json").mock(
        return_value=respx.MockResponse(404)
    )
    assert gcs.read_state().environment == "default"

    # Azure Blob
    az = AzureBlobStateBackend(
        storage_account="mystorage", container_name="iac-states", blob_name="prod.state"
    )
    respx.get("https://mystorage.blob.core.windows.net/iac-states/prod.state").mock(
        return_value=respx.MockResponse(404)
    )
    assert az.read_state().environment == "default"


def test_state_manager_factory():
    from gh_iac.core.state import (
        HttpRemoteBackend,
        LocalStateBackend,
        S3StateBackend,
        StateManager,
        create_state_backend,
    )

    local_b = create_state_backend("local", state_path="/tmp/test.json")
    assert isinstance(local_b, LocalStateBackend)

    s3_b = create_state_backend("s3", bucket="b1", key="k1")
    assert isinstance(s3_b, S3StateBackend)

    http_b = create_state_backend("http", address="https://example.com/state")
    assert isinstance(http_b, HttpRemoteBackend)

    mgr = StateManager.from_config(
        {"type": "local", "options": {"state_path": "/tmp/cfg_state.json"}}
    )
    assert isinstance(mgr.backend, LocalStateBackend)
