import os

from dotenv import load_dotenv

load_dotenv()


def get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    return value

class openai_model:
    api_key: str = get_env("OPENAI_API_KEY")
    base_url: str = "https://proxy.pieixan.icu/v1"
    model: str = "glm-5"


def get_db_uri():
    return "postgresql://postgres:qqmima123@8.155.29.72:5432/postgres"