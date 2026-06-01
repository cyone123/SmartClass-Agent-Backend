from __future__ import annotations

import contextlib
import logging
import mimetypes
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import BinaryIO, Iterator, Protocol

from app.config import (
    get_file_storage_root,
    get_minio_access_key,
    get_minio_bucket,
    get_minio_endpoint,
    get_minio_region,
    get_minio_secret_key,
    get_minio_secure,
    get_storage_backend,
    get_storage_presigned_url_ttl_seconds,
)

logger = logging.getLogger(__name__)

LOCAL_STORAGE_BACKEND = "local"
MINIO_STORAGE_BACKEND = "minio"
SAFE_KEY_PART_PATTERN = re.compile(r"[^A-Za-z0-9._=-]+")


class StorageError(RuntimeError):
    def __init__(self, message: str, *, category: str = "storage_error") -> None:
        super().__init__(message)
        self.category = category


class StorageConfigurationError(StorageError):
    def __init__(self, message: str) -> None:
        super().__init__(message, category="configuration")


@dataclass(frozen=True)
class StoredObject:
    key: str
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str | None = None
    backend: str = LOCAL_STORAGE_BACKEND
    storage_path: str | None = None


class StorageBackend(Protocol):
    backend_type: str

    def put_bytes(
        self,
        *,
        key: str,
        data: bytes,
        filename: str,
        mime_type: str,
        sha256: str | None = None,
    ) -> StoredObject:
        ...

    def put_file(
        self,
        *,
        key: str,
        source_path: Path,
        filename: str,
        mime_type: str,
        sha256: str | None = None,
    ) -> StoredObject:
        ...

    def open_stream(self, key: str) -> BinaryIO:
        ...

    def read_bytes(self, key: str) -> bytes:
        ...

    def exists(self, key: str) -> bool:
        ...

    def delete(self, key: str) -> None:
        ...

    def presigned_get_url(self, key: str, *, filename: str | None = None) -> str | None:
        ...

    @contextlib.contextmanager
    def materialize_temp_file(self, key: str, *, suffix: str = "") -> Iterator[Path]:
        ...


def _guess_mime_type(filename: str, fallback: str | None = None) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or fallback or "application/octet-stream"


def sanitize_key_part(value: object) -> str:
    text = str(value or "").replace("\\", "/").strip().strip("/")
    parts = [part for part in text.split("/") if part not in {"", ".", ".."}]
    safe = "_".join(SAFE_KEY_PART_PATTERN.sub("_", part).strip("._") for part in parts)
    return safe or "item"


def build_storage_key(*parts: object) -> str:
    safe_parts = [sanitize_key_part(part) for part in parts]
    key = "/".join(safe_parts)
    if key.startswith("/") or "/../" in f"/{key}/":
        raise StorageError("Invalid storage key.", category="invalid_key")
    return key


def _legacy_local_path(key_or_path: str) -> Path:
    return Path(key_or_path).expanduser().resolve()


class LocalStorageBackend:
    backend_type = LOCAL_STORAGE_BACKEND

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or get_file_storage_root()).resolve()

    def _resolve_key(self, key: str) -> Path:
        normalized = key.replace("\\", "/").strip().lstrip("/")
        path = (self.root / normalized).resolve()
        if path != self.root and self.root not in path.parents:
            raise StorageError("Storage key escapes local storage root.", category="invalid_key")
        return path

    def put_bytes(
        self,
        *,
        key: str,
        data: bytes,
        filename: str,
        mime_type: str,
        sha256: str | None = None,
    ) -> StoredObject:
        destination = self._resolve_key(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return StoredObject(
            key=key,
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(data),
            sha256=sha256,
            backend=self.backend_type,
            storage_path=str(destination),
        )

    def put_file(
        self,
        *,
        key: str,
        source_path: Path,
        filename: str,
        mime_type: str,
        sha256: str | None = None,
    ) -> StoredObject:
        destination = self._resolve_key(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        return StoredObject(
            key=key,
            filename=filename,
            mime_type=mime_type,
            size_bytes=destination.stat().st_size,
            sha256=sha256,
            backend=self.backend_type,
            storage_path=str(destination),
        )

    def open_stream(self, key: str) -> BinaryIO:
        path = self._resolve_key(key)
        return path.open("rb")

    def read_bytes(self, key: str) -> bytes:
        return self._resolve_key(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._resolve_key(key).is_file()

    def delete(self, key: str) -> None:
        self._resolve_key(key).unlink(missing_ok=True)

    def presigned_get_url(self, key: str, *, filename: str | None = None) -> str | None:
        _ = key, filename
        return None

    @contextlib.contextmanager
    def materialize_temp_file(self, key: str, *, suffix: str = "") -> Iterator[Path]:
        yield self._resolve_key(key)


class MinioStorageBackend:
    backend_type = MINIO_STORAGE_BACKEND

    def __init__(self) -> None:
        endpoint = get_minio_endpoint()
        bucket = get_minio_bucket()
        access_key = get_minio_access_key()
        secret_key = get_minio_secret_key()
        missing = [
            name
            for name, value in (
                ("MINIO_ENDPOINT", endpoint),
                ("MINIO_BUCKET", bucket),
                ("MINIO_ACCESS_KEY", access_key),
                ("MINIO_SECRET_KEY", secret_key),
            )
            if not value
        ]
        if missing:
            raise StorageConfigurationError(
                "Missing required MinIO configuration: " + ", ".join(missing)
            )

        try:
            from minio import Minio
            from minio.error import S3Error
        except ImportError as exc:
            raise StorageConfigurationError(
                "MinIO storage backend requires the 'minio' package."
            ) from exc

        self._s3_error_type = S3Error
        self.bucket = bucket or ""
        self.client = Minio(
            endpoint or "",
            access_key=access_key,
            secret_key=secret_key,
            secure=get_minio_secure(),
            region=get_minio_region(),
        )

    def _wrap_error(self, exc: Exception, *, operation: str) -> StorageError:
        if isinstance(exc, StorageError):
            return exc
        return StorageError(f"MinIO {operation} failed: {exc}", category=operation)

    def put_bytes(
        self,
        *,
        key: str,
        data: bytes,
        filename: str,
        mime_type: str,
        sha256: str | None = None,
    ) -> StoredObject:
        import io

        try:
            self.client.put_object(
                self.bucket,
                key,
                io.BytesIO(data),
                length=len(data),
                content_type=mime_type,
            )
        except Exception as exc:
            raise self._wrap_error(exc, operation="upload") from exc
        return StoredObject(
            key=key,
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(data),
            sha256=sha256,
            backend=self.backend_type,
            storage_path=f"minio://{self.bucket}/{key}",
        )

    def put_file(
        self,
        *,
        key: str,
        source_path: Path,
        filename: str,
        mime_type: str,
        sha256: str | None = None,
    ) -> StoredObject:
        size_bytes = source_path.stat().st_size
        try:
            self.client.fput_object(
                self.bucket,
                key,
                str(source_path),
                content_type=mime_type,
            )
        except Exception as exc:
            raise self._wrap_error(exc, operation="upload") from exc
        return StoredObject(
            key=key,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            sha256=sha256,
            backend=self.backend_type,
            storage_path=f"minio://{self.bucket}/{key}",
        )

    def open_stream(self, key: str) -> BinaryIO:
        try:
            return self.client.get_object(self.bucket, key)
        except Exception as exc:
            raise self._wrap_error(exc, operation="download") from exc

    def read_bytes(self, key: str) -> bytes:
        stream = self.open_stream(key)
        try:
            return stream.read()
        finally:
            close = getattr(stream, "close", None)
            release_conn = getattr(stream, "release_conn", None)
            if callable(close):
                close()
            if callable(release_conn):
                release_conn()

    def exists(self, key: str) -> bool:
        try:
            self.client.stat_object(self.bucket, key)
            return True
        except Exception as exc:
            code = getattr(exc, "code", "")
            if code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                return False
            raise self._wrap_error(exc, operation="stat") from exc

    def delete(self, key: str) -> None:
        try:
            self.client.remove_object(self.bucket, key)
        except Exception as exc:
            raise self._wrap_error(exc, operation="delete") from exc

    def presigned_get_url(self, key: str, *, filename: str | None = None) -> str | None:
        try:
            return self.client.presigned_get_object(
                self.bucket,
                key,
                expires=timedelta(seconds=get_storage_presigned_url_ttl_seconds()),
            )
        except Exception as exc:
            raise self._wrap_error(exc, operation="presign") from exc

    @contextlib.contextmanager
    def materialize_temp_file(self, key: str, *, suffix: str = "") -> Iterator[Path]:
        fd, temp_path_raw = tempfile.mkstemp(prefix="smartclass-storage-", suffix=suffix)
        temp_path = Path(temp_path_raw)
        try:
            with open(fd, "wb") as output_file:
                output_file.write(self.read_bytes(key))
            yield temp_path
        finally:
            temp_path.unlink(missing_ok=True)


class StorageService:
    def __init__(self, backend: StorageBackend) -> None:
        self.backend = backend
        self.local_backend = backend if isinstance(backend, LocalStorageBackend) else LocalStorageBackend()

    @property
    def backend_type(self) -> str:
        return self.backend.backend_type

    def resolve_backend(self, *, storage_backend: str | None, storage_key: str | None, storage_path: str | None) -> tuple[StorageBackend, str]:
        if storage_backend == MINIO_STORAGE_BACKEND and storage_key:
            return self.backend if self.backend.backend_type == MINIO_STORAGE_BACKEND else MinioStorageBackend(), storage_key
        if storage_key and (storage_backend in {None, "", LOCAL_STORAGE_BACKEND}):
            return self.local_backend, storage_key
        if storage_path:
            return LegacyLocalStorageBackend(), storage_path
        raise StorageError("Stored object has no storage key or legacy path.", category="missing_key")

    def put_bytes(self, **kwargs: object) -> StoredObject:
        return self._timed("upload", lambda: self.backend.put_bytes(**kwargs))  # type: ignore[arg-type]

    def put_file(self, **kwargs: object) -> StoredObject:
        return self._timed("upload", lambda: self.backend.put_file(**kwargs))  # type: ignore[arg-type]

    def read_bytes(self, *, storage_backend: str | None, storage_key: str | None, storage_path: str | None) -> bytes:
        backend, key = self.resolve_backend(
            storage_backend=storage_backend,
            storage_key=storage_key,
            storage_path=storage_path,
        )
        return self._timed("download", lambda: backend.read_bytes(key))

    def exists(self, *, storage_backend: str | None, storage_key: str | None, storage_path: str | None) -> bool:
        backend, key = self.resolve_backend(
            storage_backend=storage_backend,
            storage_key=storage_key,
            storage_path=storage_path,
        )
        return self._timed("stat", lambda: backend.exists(key))

    def delete(self, *, storage_backend: str | None, storage_key: str | None, storage_path: str | None) -> None:
        backend, key = self.resolve_backend(
            storage_backend=storage_backend,
            storage_key=storage_key,
            storage_path=storage_path,
        )
        return self._timed("delete", lambda: backend.delete(key))

    @contextlib.contextmanager
    def materialize_temp_file(
        self,
        *,
        storage_backend: str | None,
        storage_key: str | None,
        storage_path: str | None,
        suffix: str = "",
    ) -> Iterator[Path]:
        backend, key = self.resolve_backend(
            storage_backend=storage_backend,
            storage_key=storage_key,
            storage_path=storage_path,
        )
        with backend.materialize_temp_file(key, suffix=suffix) as path:
            yield path

    def presigned_get_url(
        self,
        *,
        storage_backend: str | None,
        storage_key: str | None,
        storage_path: str | None,
        filename: str | None = None,
    ) -> str | None:
        backend, key = self.resolve_backend(
            storage_backend=storage_backend,
            storage_key=storage_key,
            storage_path=storage_path,
        )
        return backend.presigned_get_url(key, filename=filename)

    def _timed(self, operation: str, callback):
        started = time.perf_counter()
        try:
            result = callback()
            logger.debug(
                "Storage operation succeeded.",
                extra={
                    "storage_backend": self.backend_type,
                    "storage_operation": operation,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                    "status": "success",
                },
            )
            return result
        except StorageError:
            logger.exception(
                "Storage operation failed.",
                extra={
                    "storage_backend": self.backend_type,
                    "storage_operation": operation,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                    "status": "failed",
                },
            )
            raise


class LegacyLocalStorageBackend:
    backend_type = LOCAL_STORAGE_BACKEND

    def put_bytes(self, **kwargs: object) -> StoredObject:
        raise StorageError("Legacy local backend is read-only.", category="unsupported")

    def put_file(self, **kwargs: object) -> StoredObject:
        raise StorageError("Legacy local backend is read-only.", category="unsupported")

    def open_stream(self, key: str) -> BinaryIO:
        return _legacy_local_path(key).open("rb")

    def read_bytes(self, key: str) -> bytes:
        return _legacy_local_path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return _legacy_local_path(key).is_file()

    def delete(self, key: str) -> None:
        _legacy_local_path(key).unlink(missing_ok=True)

    def presigned_get_url(self, key: str, *, filename: str | None = None) -> str | None:
        _ = key, filename
        return None

    @contextlib.contextmanager
    def materialize_temp_file(self, key: str, *, suffix: str = "") -> Iterator[Path]:
        _ = suffix
        yield _legacy_local_path(key)


_storage_service: StorageService | None = None
_storage_service_fingerprint: tuple[str, str] | None = None


def create_storage_service() -> StorageService:
    backend_name = get_storage_backend()
    if backend_name == LOCAL_STORAGE_BACKEND:
        backend: StorageBackend = LocalStorageBackend()
    elif backend_name == MINIO_STORAGE_BACKEND:
        backend = MinioStorageBackend()
    else:
        raise StorageConfigurationError(f"Unsupported storage backend: {backend_name}")
    return StorageService(backend)


def get_storage_service() -> StorageService:
    global _storage_service, _storage_service_fingerprint
    fingerprint = (get_storage_backend(), str(get_file_storage_root()))
    if _storage_service is None or _storage_service_fingerprint != fingerprint:
        _storage_service = create_storage_service()
        _storage_service_fingerprint = fingerprint
    return _storage_service


def reset_storage_service_for_tests() -> None:
    global _storage_service, _storage_service_fingerprint
    _storage_service = None
    _storage_service_fingerprint = None


def guess_mime_type(filename: str, fallback: str | None = None) -> str:
    return _guess_mime_type(filename, fallback)
