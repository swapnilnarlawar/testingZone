"""Azure Key Vault access and in-memory secret caching.

Authentication uses the User Assigned Managed Identity (UAMI) when
``AZURE_CLIENT_ID`` is set, and otherwise falls back to the normal
``DefaultAzureCredential`` chain (``az login``, GitHub OIDC via azure/login, ...).
Secret values are never logged.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Callable


class SecretStore:
    def __init__(self, vault_url: str, client_id: str | None = None, credential=None):
        from azure.keyvault.secrets import SecretClient

        if credential is None:
            from azure.identity import DefaultAzureCredential

            credential = (
                DefaultAzureCredential(managed_identity_client_id=client_id)
                if client_id
                else DefaultAzureCredential()
            )
        self._client = SecretClient(vault_url=vault_url, credential=credential)

    def get(self, name: str) -> str | None:
        secret = self.get_with_tags(name)
        return secret[0] if secret else None

    def get_with_tags(self, name: str) -> tuple[str, dict] | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            secret = self._client.get_secret(name)
        except ResourceNotFoundError:
            return None
        return secret.value, dict(secret.properties.tags or {})

    def set(self, name: str, value: str, tags: dict | None = None) -> None:
        self._client.set_secret(name, value, tags=tags or {}, content_type="text/plain")


def previous_secret_is_valid(tags: dict, now: datetime | None = None) -> bool:
    """The ``-previous`` webhook secret is accepted until its ``expires_at`` tag."""
    expires = (tags or {}).get("expires_at")
    if not expires:
        return False
    try:
        expires_at = datetime.fromisoformat(expires)
    except ValueError:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return (now or datetime.now(timezone.utc)) < expires_at


class CachedValue:
    """Caches a loaded value for ``ttl`` seconds.

    ``get(refresh=True)`` forces a reload, but at most once every
    ``min_refresh_interval`` seconds so bad requests cannot hammer Key Vault.
    """

    def __init__(self, loader: Callable[[], object], ttl: float = 300, min_refresh_interval: float = 30,
                 clock: Callable[[], float] = time.monotonic):
        self._loader = loader
        self._ttl = ttl
        self._min_refresh = min_refresh_interval
        self._clock = clock
        self._lock = threading.Lock()
        self._value = None
        self._loaded_at: float | None = None

    def get(self, refresh: bool = False):
        with self._lock:
            now = self._clock()
            age = None if self._loaded_at is None else now - self._loaded_at
            if age is None or age >= self._ttl or (refresh and age >= self._min_refresh):
                self._value = self._loader()
                self._loaded_at = now
            return self._value
