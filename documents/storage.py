"""Fernet-encrypted private file storage service (encrypt on save, decrypt on download).

Bytes are encrypted before they are persisted and decrypted when read; nothing is
ever served from a public URL. ``settings.PRIVATE_STORAGE`` picks where the
encrypted bytes live:

* ``"database"`` (default) - the ``StoredFile`` table in PostgreSQL. Survives
  redeploys on hosts with an ephemeral disk such as Render.
* ``"filesystem"`` - files under ``settings.PRIVATE_MEDIA_ROOT``.
"""
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, Storage
from django.utils.deconstruct import deconstructible


@lru_cache(maxsize=4)
def _fernet_for(key):
    if not key:
        raise ImproperlyConfigured(
            "FIELD_ENCRYPTION_KEY is not set. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY is not a valid Fernet key.") from exc


def get_fernet():
    return _fernet_for(settings.FIELD_ENCRYPTION_KEY)


def encrypt_bytes(data: bytes) -> bytes:
    return get_fernet().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    try:
        return get_fernet().decrypt(token)
    except InvalidToken as exc:
        raise ValueError("Stored file could not be decrypted (wrong key or corrupted file).") from exc


class _FilesystemBackend:
    def _fs(self):
        return FileSystemStorage(location=os.path.abspath(settings.PRIVATE_MEDIA_ROOT), base_url=None)

    def save_raw(self, name, token):
        return self._fs()._save(name, ContentFile(token))

    def read_raw(self, name):
        with self._fs().open(name, "rb") as fh:
            return fh.read()

    def exists(self, name):
        return self._fs().exists(name)

    def delete(self, name):
        self._fs().delete(name)

    def size(self, name):
        return self._fs().size(name)

    def path(self, name):
        return self._fs().path(name)


class _DatabaseBackend:
    @staticmethod
    def _model():
        from .models import StoredFile  # late import: this module is imported by documents.models

        return StoredFile

    def save_raw(self, name, token):
        self._model().objects.create(name=name, data=token, size=len(token))
        return name

    def read_raw(self, name):
        try:
            return bytes(self._model().objects.values_list("data", flat=True).get(name=name))
        except self._model().DoesNotExist as exc:
            raise FileNotFoundError(name) from exc

    def exists(self, name):
        return self._model().objects.filter(name=name).exists()

    def delete(self, name):
        self._model().objects.filter(name=name).delete()

    def size(self, name):
        try:
            return self._model().objects.values_list("size", flat=True).get(name=name)
        except self._model().DoesNotExist as exc:
            raise FileNotFoundError(name) from exc

    def path(self, name):
        raise NotImplementedError("Files stored in the database have no filesystem path.")


_BACKENDS = {"database": _DatabaseBackend(), "filesystem": _FilesystemBackend()}


@deconstructible
class EncryptedPrivateStorage(Storage):
    """Encrypts content at rest; has no public URL. Backend chosen by settings.PRIVATE_STORAGE."""

    def backend(self):
        try:
            return _BACKENDS[settings.PRIVATE_STORAGE]
        except KeyError as exc:
            raise ImproperlyConfigured("PRIVATE_STORAGE must be 'database' or 'filesystem'.") from exc

    def _save(self, name, content):
        if hasattr(content, "seek"):
            content.seek(0)
        data = b"".join(content.chunks()) if hasattr(content, "chunks") else content.read()
        return self.backend().save_raw(name, encrypt_bytes(data))

    def _open(self, name, mode="rb"):
        return ContentFile(decrypt_bytes(self.read_raw(name)), name=name)

    def read_raw(self, name) -> bytes:
        """The encrypted bytes exactly as stored."""
        return self.backend().read_raw(name)

    def read_decrypted(self, name) -> bytes:
        return decrypt_bytes(self.read_raw(name))

    def exists(self, name):
        return self.backend().exists(name)

    def delete(self, name):
        self.backend().delete(name)

    def size(self, name):
        return self.backend().size(name)

    def path(self, name):
        return self.backend().path(name)

    def url(self, name):
        raise ValueError("Private documents are not served from a public URL.")


private_storage = EncryptedPrivateStorage()


def get_private_storage():
    return private_storage
