from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    base_domain: str = "jameshomelab.org"
    secret_key: str = "change-me"
    public_host: str = "home.jameshomelab.org"


@lru_cache
def get_settings() -> Settings:
    return Settings()
