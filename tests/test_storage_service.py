from __future__ import annotations

from pathlib import Path
import tempfile

import pytest

from app.core import storage
from app.core.storage import (
    LOCAL_STORAGE_BACKEND,
    MINIO_STORAGE_BACKEND,
    LocalStorageBackend,
    StorageConfigurationError,
    StorageService,
    StoredObject,
    build_storage_key,
)


def test_local_storage_backend_put_read_materialize_and_delete(tmp_path: Path) -> None:
    service = StorageService(LocalStorageBackend(tmp_path))
    key = build_storage_key("attachments", "thread-1", "../lesson.pdf")

    stored = service.put_bytes(
        key=key,
        data=b"pdf-bytes",
        filename="lesson.pdf",
        mime_type="application/pdf",
        sha256="a" * 64,
    )

    assert stored.backend == LOCAL_STORAGE_BACKEND
    assert stored.storage_path is not None
    assert Path(stored.storage_path).read_bytes() == b"pdf-bytes"
    assert service.exists(storage_backend=stored.backend, storage_key=stored.key, storage_path=stored.storage_path)
    assert service.read_bytes(storage_backend=stored.backend, storage_key=stored.key, storage_path=stored.storage_path) == b"pdf-bytes"

    with service.materialize_temp_file(
        storage_backend=stored.backend,
        storage_key=stored.key,
        storage_path=stored.storage_path,
        suffix=".pdf",
    ) as materialized:
        assert materialized == Path(stored.storage_path)

    service.delete(storage_backend=stored.backend, storage_key=stored.key, storage_path=stored.storage_path)
    assert not Path(stored.storage_path).exists()


def test_legacy_local_path_fallback(tmp_path: Path) -> None:
    legacy_path = tmp_path / "legacy.txt"
    legacy_path.write_text("legacy", encoding="utf-8")
    service = StorageService(LocalStorageBackend(tmp_path / "root"))

    assert service.exists(storage_backend=None, storage_key=None, storage_path=str(legacy_path))
    assert service.read_bytes(storage_backend=None, storage_key=None, storage_path=str(legacy_path)) == b"legacy"


def test_build_storage_key_rejects_traversal_shape() -> None:
    key = build_storage_key("artifacts", "..", "C:\\tmp\\file.html")

    assert ".." not in key.split("/")
    assert not key.startswith("/")
    assert "\\" not in key


def test_minio_configuration_validation(monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "minio")
    monkeypatch.delenv("MINIO_ENDPOINT", raising=False)
    monkeypatch.delenv("MINIO_BUCKET", raising=False)
    monkeypatch.delenv("MINIO_ACCESS_KEY", raising=False)
    monkeypatch.delenv("MINIO_SECRET_KEY", raising=False)
    storage.reset_storage_service_for_tests()

    with pytest.raises(StorageConfigurationError):
        storage.get_storage_service()


class FakeMinioBackend:
    backend_type = MINIO_STORAGE_BACKEND

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_bytes(self, *, key, data, filename, mime_type, sha256=None):
        self.objects[key] = data
        return StoredObject(
            key=key,
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(data),
            sha256=sha256,
            backend=self.backend_type,
            storage_path=f"minio://bucket/{key}",
        )

    def put_file(self, *, key, source_path, filename, mime_type, sha256=None):
        return self.put_bytes(
            key=key,
            data=Path(source_path).read_bytes(),
            filename=filename,
            mime_type=mime_type,
            sha256=sha256,
        )

    def open_stream(self, key):
        raise NotImplementedError

    def read_bytes(self, key):
        return self.objects[key]

    def exists(self, key):
        return key in self.objects

    def delete(self, key):
        self.objects.pop(key, None)

    def presigned_get_url(self, key, *, filename=None):
        _ = filename
        return f"https://minio.example.test/{key}"

    def materialize_temp_file(self, key, *, suffix=""):
        class TempPathContext:
            def __enter__(self_inner):
                with tempfile.NamedTemporaryFile(prefix="fake-minio-", suffix=suffix or ".tmp", delete=False) as file:
                    self_inner.path = Path(file.name)
                self_inner.path.write_bytes(self.objects[key])
                return self_inner.path

            def __exit__(self_inner, exc_type, exc, tb):
                self_inner.path.unlink(missing_ok=True)
                return False

        return TempPathContext()


def test_storage_service_accepts_minio_like_backend(tmp_path: Path) -> None:
    service = StorageService(FakeMinioBackend())
    source = tmp_path / "artifact.html"
    source.write_text("<html></html>", encoding="utf-8")
    key = build_storage_key("artifacts", "thread-1", "run-1", "artifact.html")

    stored = service.put_file(
        key=key,
        source_path=source,
        filename="artifact.html",
        mime_type="text/html",
    )

    assert stored.backend == MINIO_STORAGE_BACKEND
    assert service.exists(storage_backend=MINIO_STORAGE_BACKEND, storage_key=key, storage_path=stored.storage_path)
    assert service.read_bytes(storage_backend=MINIO_STORAGE_BACKEND, storage_key=key, storage_path=stored.storage_path) == b"<html></html>"
    assert service.presigned_get_url(storage_backend=MINIO_STORAGE_BACKEND, storage_key=key, storage_path=stored.storage_path) == f"https://minio.example.test/{key}"
