import os
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
