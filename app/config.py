from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DASHBOARD_", env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000
    title: str = "Skynet Cluster Dashboard"
    # Later: discover apps via Kubernetes / a configmap; stubs for now
    cards_json: str = ""


settings = Settings()
