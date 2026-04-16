from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from uuid import uuid4

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("MODEL", "test-model")
os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("BASE_URL", "https://example.com")
os.environ.setdefault("STRUCTED_MDOEL", "test-model")
os.environ.setdefault("STRUCTED_API_KEY", "test-key")
os.environ.setdefault("STRUCTED_BASE_URL", "https://example.com")
os.environ.setdefault("SMALL_MDOEL", "test-model")
os.environ.setdefault("SMALL_API_KEY", "test-key")
os.environ.setdefault("SMALL_BASE_URL", "https://example.com")
os.environ.setdefault("STT_MODEL", "test-stt-model")
os.environ.setdefault("STT_API_KEY", "test-key")
os.environ.setdefault("STT_BASE_URL", "https://example.com")
for proxy_key in (
    "ALL_PROXY",
    "all_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
    "NO_PROXY",
    "no_proxy",
):
    os.environ.pop(proxy_key, None)


@pytest.fixture
def tmp_path() -> Path:
    path = BACKEND_ROOT / "storage" / "pytest_tmp" / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
