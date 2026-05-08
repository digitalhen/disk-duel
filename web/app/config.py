from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    disk_duel_api_key: str = ""  # reserved for future admin endpoints
    hashids_salt: str
    root_path: str = ""
    public_base_url: str = "http://localhost:8000"

    # Anti-spam knobs. PoW must match what the published script computes;
    # bumping this rejects older scripts. Rate-limit per serial enforces
    # a minimum gap between runs from the same machine.
    pow_difficulty_bits: int = 20
    serial_cooldown_seconds: int = 60
    ip_limit_per_minute: int = 30

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()  # type: ignore[call-arg]
