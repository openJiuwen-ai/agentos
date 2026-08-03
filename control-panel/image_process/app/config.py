"""Service configuration."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    HOST: str = "0.0.0.0"
    PORT: int = 8091
    # Drop finished in-memory build records after this many seconds.
    TASK_TTL_SECONDS: int = 24 * 3600


settings = Settings()
