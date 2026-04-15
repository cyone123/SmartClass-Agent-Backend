import os
from pathlib import Path
from urllib.parse import quote, urlparse

from dotenv import load_dotenv

load_dotenv()


def get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    return value


def get_db_uri() -> str:
    database_url = get_env("DATABASE_URL") or get_env("POSTGRES_URL")
    if database_url:
        return database_url

    raw_host = get_env("DB_HOST", "localhost") or "localhost"
    parsed = urlparse(raw_host if "://" in raw_host else f"//{raw_host}")
    host = parsed.hostname or raw_host.split(":")[0]
    port = parsed.port or int(get_env("DB_PORT", "5432") or "5432")
    database = get_env("DB_NAME") or get_env("POSTGRES_DB") or "postgres"
    user = quote(get_env("DB_USER", "postgres") or "postgres")
    password = quote(get_env("DB_PASSWORD", "") or "")
    sslmode = get_env("DB_SSLMODE")

    conn_string = f"postgresql://{user}:{password}@{host}:{port}/{database}"
    if sslmode:
        conn_string = f"{conn_string}?sslmode={sslmode}"
    return conn_string


def get_backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_skills_root() -> Path:
    configured = get_env("SKILLS_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return get_backend_root() / "skills"


def get_file_storage_root() -> Path:
    configured = get_env("FILE_STORAGE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return get_backend_root() / "storage"


def get_public_api_base_url() -> str | None:
    configured = get_env("PUBLIC_API_BASE_URL")
    if configured is None:
        return None

    normalized = configured.strip().rstrip("/")
    return normalized or None


def get_file_upload_max_size_bytes() -> int:
    value = get_env("FILE_UPLOAD_MAX_SIZE_BYTES", "20971520") or "20971520"
    return int(value)


def get_allowed_upload_extensions() -> set[str]:
    raw = get_env("FILE_ALLOWED_EXTENSIONS", ".docx,.pdf") or ".docx,.pdf,.mp4"
    return {
        extension.strip().lower()
        for extension in raw.split(",")
        if extension.strip()
    }
