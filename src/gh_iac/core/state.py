"""State storage, backends, locking, and AES-GCM encryption for GitHub IaC."""

import hashlib
import json
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional, Union

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, Field


class StateLockError(Exception):
    """Raised when an operation cannot proceed due to an existing state lock."""
    pass


class ResourceState(BaseModel):
    """Recorded state for an individual GitHub resource."""
    resource_id: str
    kind: str
    node_id: Optional[str] = None  # GitHub GraphQL Global Node ID
    numeric_id: Optional[Union[int, str]] = None
    url: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    applied_spec: Dict[str, Any] = Field(default_factory=dict)
    last_updated: Optional[str] = None


class StateFile(BaseModel):
    """Root model for serialized state files."""
    version: str = "1"
    environment: str
    resources: Dict[str, ResourceState] = Field(default_factory=dict)


class BaseStateBackend(ABC):
    """Abstract interface for pluggable state backends."""

    @abstractmethod
    def read_state(self) -> StateFile:
        """Read and deserialize the state file."""
        pass

    @abstractmethod
    def write_state(self, state: StateFile) -> None:
        """Serialize and persist the state file."""
        pass

    @abstractmethod
    def lock(self) -> None:
        """Acquire an exclusive lock."""
        pass

    @abstractmethod
    def unlock(self) -> None:
        """Release the exclusive lock."""
        pass

    @abstractmethod
    def is_locked(self) -> bool:
        """Check whether the backend is locked."""
        pass



def serialize_state(state: StateFile, passphrase: Optional[str] = None) -> bytes:
    """Serialize StateFile to bytes, with optional AES-GCM encryption."""
    json_bytes = state.model_dump_json(indent=2).encode("utf-8")
    if passphrase:
        key = hashlib.sha256(passphrase.encode("utf-8")).digest()
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, json_bytes, None)
        return nonce + ciphertext
    return json_bytes


def deserialize_state(raw_bytes: bytes, passphrase: Optional[str] = None) -> StateFile:
    """Deserialize bytes to StateFile, with optional AES-GCM decryption."""
    if not raw_bytes:
        return StateFile(environment="default")

    if passphrase:
        try:
            nonce = raw_bytes[:12]
            ciphertext = raw_bytes[12:]
            key = hashlib.sha256(passphrase.encode("utf-8")).digest()
            aesgcm = AESGCM(key)
            decrypted = aesgcm.decrypt(nonce, ciphertext, None)
            data = json.loads(decrypted.decode("utf-8"))
        except Exception as e:
            raise ValueError(f"Failed to decrypt state file: invalid passphrase or corrupted data ({e})") from e
    else:
        data = json.loads(raw_bytes.decode("utf-8"))

    return StateFile.model_validate(data)


class LocalStateBackend(BaseStateBackend):
    """
    Local filesystem state backend supporting optional AES-GCM encryption
    and lockfile concurrency control.
    """

    def __init__(
        self,
        state_path: Union[str, Path] = "gh-iac.state.json",
        passphrase: Optional[str] = None,
    ):
        self.state_path = Path(state_path)
        self.lock_path = Path(f"{self.state_path}.lock")
        self.passphrase = passphrase or os.environ.get("GITHUB_IAC_STATE_PASSPHRASE")

    def read_state(self) -> StateFile:
        if not self.state_path.exists():
            return StateFile(environment="default")

        raw_bytes = self.state_path.read_bytes()
        return deserialize_state(raw_bytes, self.passphrase)

    def write_state(self, state: StateFile) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        raw_bytes = serialize_state(state, self.passphrase)
        self.state_path.write_bytes(raw_bytes)

    def lock(self) -> None:
        if self.is_locked():
            raise StateLockError(f"State file '{self.state_path}' is locked by another process.")
        lock_data = {"pid": os.getpid(), "timestamp": time.time()}
        self.lock_path.write_text(json.dumps(lock_data), encoding="utf-8")

    def unlock(self) -> None:
        if self.lock_path.exists():
            self.lock_path.unlink()

    def is_locked(self) -> bool:
        return self.lock_path.exists()


class HttpRemoteBackend(BaseStateBackend):
    """
    HTTP REST remote state backend supporting state locking and AES-GCM encryption.
    Compatible with Terraform HTTP state backend protocol.
    """

    def __init__(
        self,
        address: str,
        lock_address: Optional[str] = None,
        unlock_address: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        passphrase: Optional[str] = None,
    ):
        import httpx

        self.address = address
        self.lock_address = lock_address or f"{address.rstrip('/')}/lock"
        self.unlock_address = unlock_address or self.lock_address
        self.headers = headers or {}
        self.passphrase = passphrase or os.environ.get("GITHUB_IAC_STATE_PASSPHRASE")
        self._client = httpx.Client(headers=self.headers, timeout=30.0)

    def read_state(self) -> StateFile:
        resp = self._client.get(self.address)
        if resp.status_code == 404:
            return StateFile(environment="default")
        resp.raise_for_status()
        return deserialize_state(resp.content, self.passphrase)

    def write_state(self, state: StateFile) -> None:
        content = serialize_state(state, self.passphrase)
        resp = self._client.put(self.address, content=content)
        resp.raise_for_status()

    def lock(self) -> None:
        payload = {"id": os.urandom(8).hex(), "who": f"pid:{os.getpid()}", "timestamp": time.time()}
        resp = self._client.post(self.lock_address, json=payload)
        if resp.status_code in (409, 423):
            raise StateLockError(f"Remote state at '{self.address}' is locked by another process.")
        resp.raise_for_status()

    def unlock(self) -> None:
        resp = self._client.request("DELETE", self.unlock_address)
        if resp.status_code not in (200, 204, 404):
            resp.raise_for_status()

    def is_locked(self) -> bool:
        resp = self._client.get(self.lock_address)
        return resp.status_code == 200


class S3StateBackend(BaseStateBackend):
    """
    Amazon S3 remote state backend with object-level lockfile coordination
    and AES-GCM client-side encryption.
    """

    def __init__(
        self,
        bucket: str,
        key: str = "github-iac/state.json",
        region: str = "us-east-1",
        endpoint_url: Optional[str] = None,
        passphrase: Optional[str] = None,
    ):
        import httpx

        self.bucket = bucket
        self.key = key.lstrip("/")
        self.region = region
        self.endpoint_url = endpoint_url
        self.passphrase = passphrase or os.environ.get("GITHUB_IAC_STATE_PASSPHRASE")

        if endpoint_url:
            self.base_url = f"{endpoint_url.rstrip('/')}/{self.bucket}/{self.key}"
        else:
            self.base_url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{self.key}"

        self.lock_url = f"{self.base_url}.lock"
        self._client = httpx.Client(timeout=30.0)

    def read_state(self) -> StateFile:
        resp = self._client.get(self.base_url)
        if resp.status_code == 404:
            return StateFile(environment="default")
        resp.raise_for_status()
        return deserialize_state(resp.content, self.passphrase)

    def write_state(self, state: StateFile) -> None:
        content = serialize_state(state, self.passphrase)
        resp = self._client.put(self.base_url, content=content)
        resp.raise_for_status()

    def lock(self) -> None:
        if self.is_locked():
            raise StateLockError(f"S3 state '{self.base_url}' is locked.")
        lock_data = json.dumps({"pid": os.getpid(), "timestamp": time.time()}).encode("utf-8")
        resp = self._client.put(self.lock_url, content=lock_data)
        resp.raise_for_status()

    def unlock(self) -> None:
        resp = self._client.delete(self.lock_url)
        if resp.status_code not in (200, 204, 404):
            resp.raise_for_status()

    def is_locked(self) -> bool:
        resp = self._client.get(self.lock_url)
        return resp.status_code == 200


class GCSStateBackend(BaseStateBackend):
    """
    Google Cloud Storage (GCS) remote state backend with AES-GCM encryption
    and lockfile concurrency control.
    """

    def __init__(
        self,
        bucket: str,
        blob_name: str = "github-iac/state.json",
        passphrase: Optional[str] = None,
    ):
        import httpx

        self.bucket = bucket
        self.blob_name = blob_name.lstrip("/")
        self.passphrase = passphrase or os.environ.get("GITHUB_IAC_STATE_PASSPHRASE")
        self.base_url = f"https://storage.googleapis.com/{self.bucket}/{self.blob_name}"
        self.lock_url = f"{self.base_url}.lock"
        self._client = httpx.Client(timeout=30.0)

    def read_state(self) -> StateFile:
        resp = self._client.get(self.base_url)
        if resp.status_code == 404:
            return StateFile(environment="default")
        resp.raise_for_status()
        return deserialize_state(resp.content, self.passphrase)

    def write_state(self, state: StateFile) -> None:
        content = serialize_state(state, self.passphrase)
        resp = self._client.put(self.base_url, content=content)
        resp.raise_for_status()

    def lock(self) -> None:
        if self.is_locked():
            raise StateLockError(f"GCS state '{self.base_url}' is locked.")
        lock_data = json.dumps({"pid": os.getpid(), "timestamp": time.time()}).encode("utf-8")
        resp = self._client.put(self.lock_url, content=lock_data)
        resp.raise_for_status()

    def unlock(self) -> None:
        resp = self._client.delete(self.lock_url)
        if resp.status_code not in (200, 204, 404):
            resp.raise_for_status()

    def is_locked(self) -> bool:
        resp = self._client.get(self.lock_url)
        return resp.status_code == 200


class AzureBlobStateBackend(BaseStateBackend):
    """
    Azure Blob Storage remote state backend with AES-GCM encryption
    and lockfile concurrency control.
    """

    def __init__(
        self,
        storage_account: str,
        container_name: str,
        blob_name: str = "github-iac/state.json",
        passphrase: Optional[str] = None,
    ):
        import httpx

        self.storage_account = storage_account
        self.container_name = container_name
        self.blob_name = blob_name.lstrip("/")
        self.passphrase = passphrase or os.environ.get("GITHUB_IAC_STATE_PASSPHRASE")
        self.base_url = f"https://{self.storage_account}.blob.core.windows.net/{self.container_name}/{self.blob_name}"
        self.lock_url = f"{self.base_url}.lock"
        self._client = httpx.Client(timeout=30.0)

    def read_state(self) -> StateFile:
        resp = self._client.get(self.base_url)
        if resp.status_code == 404:
            return StateFile(environment="default")
        resp.raise_for_status()
        return deserialize_state(resp.content, self.passphrase)

    def write_state(self, state: StateFile) -> None:
        content = serialize_state(state, self.passphrase)
        resp = self._client.put(self.base_url, content=content, headers={"x-ms-blob-type": "BlockBlob"})
        resp.raise_for_status()

    def lock(self) -> None:
        if self.is_locked():
            raise StateLockError(f"Azure blob state '{self.base_url}' is locked.")
        lock_data = json.dumps({"pid": os.getpid(), "timestamp": time.time()}).encode("utf-8")
        resp = self._client.put(
            self.lock_url,
            content=lock_data,
            headers={"x-ms-blob-type": "BlockBlob"},
        )
        resp.raise_for_status()

    def unlock(self) -> None:
        resp = self._client.delete(self.lock_url)
        if resp.status_code not in (200, 204, 404):
            resp.raise_for_status()

    def is_locked(self) -> bool:
        resp = self._client.get(self.lock_url)
        return resp.status_code == 200


def create_state_backend(backend_type: str = "local", **kwargs: Any) -> BaseStateBackend:
    """Factory creating configured state backends."""
    b_type = backend_type.lower()
    if b_type == "local":
        return LocalStateBackend(
            state_path=kwargs.get("state_path", "gh-iac.state.json"),
            passphrase=kwargs.get("passphrase"),
        )
    elif b_type == "http":
        return HttpRemoteBackend(
            address=kwargs["address"],
            lock_address=kwargs.get("lock_address"),
            unlock_address=kwargs.get("unlock_address"),
            headers=kwargs.get("headers"),
            passphrase=kwargs.get("passphrase"),
        )
    elif b_type == "s3":
        return S3StateBackend(
            bucket=kwargs["bucket"],
            key=kwargs.get("key", "github-iac/state.json"),
            region=kwargs.get("region", "us-east-1"),
            endpoint_url=kwargs.get("endpoint_url"),
            passphrase=kwargs.get("passphrase"),
        )
    elif b_type == "gcs":
        return GCSStateBackend(
            bucket=kwargs["bucket"],
            blob_name=kwargs.get("blob_name", "github-iac/state.json"),
            passphrase=kwargs.get("passphrase"),
        )
    elif b_type in ("azure", "azureblob"):
        return AzureBlobStateBackend(
            storage_account=kwargs["storage_account"],
            container_name=kwargs["container_name"],
            blob_name=kwargs.get("blob_name", "github-iac/state.json"),
            passphrase=kwargs.get("passphrase"),
        )
    else:
        raise ValueError(f"Unsupported state backend type: '{backend_type}'. Choose local, http, s3, gcs, or azure.")


class StateManager:
    """Manages reading and persisting IaC resource state via pluggable backends."""

    def __init__(
        self,
        state_path: Union[str, Path] = "gh-iac.state.json",
        backend: Optional[BaseStateBackend] = None,
    ):
        self.backend = backend or LocalStateBackend(state_path=state_path)
        self.state = StateFile(environment="default")
        self.load()

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "StateManager":
        backend_type = config.get("type", "local")
        backend = create_state_backend(backend_type, **config.get("options", {}))
        return cls(backend=backend)

    def load(self) -> None:
        self.state = self.backend.read_state()

    def save(self) -> None:
        self.backend.write_state(self.state)

    def get_resource(self, resource_id: str) -> Optional[ResourceState]:
        return self.state.resources.get(resource_id)

    def set_resource(self, resource_id: str, state: ResourceState) -> None:
        self.state.resources[resource_id] = state

    def remove_resource(self, resource_id: str) -> None:
        if resource_id in self.state.resources:
            del self.state.resources[resource_id]
