"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # ── Database (必须从 .env 读取) ──
    DATABASE_URL: str = ""

    # ── Initial admin (必须从 .env 读取) ──
    AGENTOS_ADMIN_USERNAME: str = ""
    AGENTOS_ADMIN_PASSWORD: str = ""

    # ── User system backend selection ──
    USER_SYSTEM_BACKEND: str = "local-users"

    # ── Home directories ──
    AGENTOS_HOME_BASE: str = "/home"

    # ── Logging ──
    LOG_DIR: str = "logs"
    LOG_MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB
    LOG_BACKUP_COUNT: int = 5

    def validate_required(self) -> None:
        """校验必填配置项，启动时调用。"""
        missing = []
        if not self.DATABASE_URL:
            missing.append("DATABASE_URL")
        if not self.AGENTOS_ADMIN_USERNAME:
            missing.append("AGENTOS_ADMIN_USERNAME")
        if not self.AGENTOS_ADMIN_PASSWORD:
            missing.append("AGENTOS_ADMIN_PASSWORD")
        if missing:
            raise ValueError(
                f"缺少必填配置: {', '.join(missing)}。"
                f"请在 .env 文件中设置。参考 .env.example"
            )


settings = Settings()
