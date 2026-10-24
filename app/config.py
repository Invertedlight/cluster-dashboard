from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    base_domain: str = "jameshomelab.org"
    secret_key: str = "change-me"
    public_host: str = "home.jameshomelab.org"

    # Edit login (0.4.0). All four must be set or editing stays disabled.
    admin_username: str = ""
    admin_password_hash: str = ""
    session_secret: str = ""
    totp_secret: str = ""
    session_max_age: int = 12 * 60 * 60
    session_cookie_secure: bool = True
    # Only peers in these networks may supply CF-Connecting-IP / X-Forwarded-For.
    trusted_proxies: str = "10.42.0.0/16,127.0.0.1/32"
    login_max_failures: int = 5
    login_window_seconds: int = 15 * 60
    login_lockout_seconds: int = 15 * 60

    @property
    def auth_configured(self) -> bool:
        return all(
            v.strip()
            for v in (self.admin_username, self.admin_password_hash, self.session_secret, self.totp_secret)
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
