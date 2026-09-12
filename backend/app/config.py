from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://archaeo:archaeo@localhost:5432/archaeo"
    redis_url: str = "redis://localhost:6379/0"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "archaeo-photos"
    minio_secure: bool = False
    minio_public_endpoint: str = "http://localhost:9000"

    cache_ttl_seconds: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
