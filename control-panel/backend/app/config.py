"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # ── Database (必须从 .env 读取) ──
    AGENTOS_DATABASE_URL: str = ""

    # ── JWT (auth module) ──
    AGENTOS_JWT_SECRET_KEY: str = ""
    AGENTOS_JWT_ALGORITHM: str = "HS256"
    AGENTOS_JWT_ACCESS_EXPIRE_MINUTES: int = 15
    AGENTOS_JWT_REFRESH_EXPIRE_DAYS: int = 7

    # ── Initial admin (必须从 .env 读取) ──
    AGENTOS_ADMIN_USERNAME: str = ""
    AGENTOS_ADMIN_PASSWORD: str = ""

    # ── User system backend selection ──
    USER_SYSTEM_BACKEND: str = "local-users"

    # ── Home directories ──
    AGENTOS_HOME_BASE: str = "/home/agentos/users"

    # ── Logging ──
    LOG_DIR: str = "/home/agentos/logs"
    LOG_MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB
    LOG_BACKUP_COUNT: int = 5

    # ── VictoriaMetrics agent metrics config ──
    AGENT_METRICS_CONFIG_PATH: str = "/etc/vm/agent-metrics.json"

    # ── LiteLLM (必须从 .env 读取) ──
    LITELLM_ADMIN_URL: str = ""
    LITELLM_MASTER_KEY: str = ""
    LITELLM_KEY_ENCRYPTION_KEY: str = (
        ""  # 256-bit AES-GCM key (64 hex chars). Generate: openssl rand -hex 32
    )
    MAX_KEYS_PER_USER: int = 10
    LITELLM_REQUEST_TIMEOUT: float = 30.0
    LITELLM_DATABASE_URL: str = ""

    def validate_required(self) -> None:
        """校验必填配置项，启动时调用。"""
        required = [
            "AGENTOS_DATABASE_URL",
            "AGENTOS_JWT_SECRET_KEY",
            "AGENTOS_ADMIN_USERNAME",
            "AGENTOS_ADMIN_PASSWORD",
            "LITELLM_ADMIN_URL",
            "LITELLM_MASTER_KEY",
            "LITELLM_KEY_ENCRYPTION_KEY",
            "LITELLM_DATABASE_URL",
        ]
        missing = [name for name in required if not getattr(self, name)]
        if missing:
            raise ValueError(
                f"缺少必填配置: {', '.join(missing)}。"
                f"请在 .env 文件中设置。参考 .env.example"
            )


settings = Settings()
