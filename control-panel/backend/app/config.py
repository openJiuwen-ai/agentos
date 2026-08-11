"""Application configuration loaded from environment variables."""

import json

from pydantic import field_validator

from pydantic_settings import BaseSettings

from app.models.monitor_node import (
    MASTER_NODE_ID,
    MASTER_ROLE,
    WORKER_ROLE,
    ConfiguredHardwareNode,
    MonitorNodeConfig,
    NodeTarget,
)


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
    AGENTOS_SWARM_TEMPLATE_DIR: str = "/root/.jiuwenswarm"

    # ── Logging ──
    LOG_DIR: str = "/home/agentos/logs"
    LOG_MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB
    LOG_BACKUP_COUNT: int = 5

    # ── Log Center ──
    LOG_EXPORT_PATH: str = "/var/log/agentos"
    LOG_INITIAL_TAIL_LINES: int = 100
    LOG_MAX_LINE_LENGTH: int = 10000
    LOG_MAX_FILES_PER_WS: int = 5
    LOG_EXPORT_MAX_CONCURRENT: int = 2
    LOG_EXPORT_RETENTION_DAYS: int = 7
    LOG_EXPORT_CLEANUP_HOUR: int = 3
    LOG_EXPORT_MAX_SIZE_BYTES: int = 536_870_912  # 512 MB
    # ── Thirdparty Agents ──
    AGENTOS_COMMON: str = "/home/agentos/common"  # shared resources directory for agent images
    THIRDPARTY_AGENT_INSTALLER_MAX_BYTES: int = 524_288_000  # 500 MB
    AGENT_IMAGE_MODULE_VERSION: str = "1.0"         # 镜像模块版本

    # ── image_process (standalone builder; required, no in-process fallback) ──
    IMAGE_PROCESS_URL: str = ""  # e.g. http://image-process:8091
    IMAGE_PROCESS_TIMEOUT_SECONDS: float = 30.0

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

    # ── Hardware monitoring ──
    NPU_EXPORTER_HOST: str = "host.docker.internal"
    NPU_EXPORTER_PORT: int = 8092
    NODE_EXPORTER_HOST: str = "host.docker.internal"
    NODE_EXPORTER_PORT: int = 8091
    WORKER_NODES: str = ""
    VICTORIAMETRICS_URL: str = ""

    @property
    def npu_exporter_url(self) -> str:
        return f"http://{self.NPU_EXPORTER_HOST}:{self.NPU_EXPORTER_PORT}"

    @property
    def node_exporter_url(self) -> str:
        return f"http://{self.NODE_EXPORTER_HOST}:{self.NODE_EXPORTER_PORT}"

    @property
    def worker_nodes(self) -> list[MonitorNodeConfig]:
        raw = self.WORKER_NODES.strip()
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        nodes: list[MonitorNodeConfig] = []
        seen: set[str] = set()
        master_host = self.NODE_EXPORTER_HOST.strip()
        for item in data:
            if not isinstance(item, str):
                continue
            host = item.strip()
            if not host or host in seen:
                continue
            if master_host and host == master_host:
                continue
            seen.add(host)
            nodes.append(MonitorNodeConfig(host=host))
        return nodes

    @property
    def configured_hardware_nodes(self) -> list[ConfiguredHardwareNode]:
        nodes: list[ConfiguredHardwareNode] = [
            ConfiguredHardwareNode(
                id=MASTER_NODE_ID,
                host=self.NODE_EXPORTER_HOST,
                role=MASTER_ROLE,
                vm_label=MASTER_NODE_ID,
            )
        ]
        for index, worker in enumerate(self.worker_nodes, start=1):
            nodes.append(
                ConfiguredHardwareNode(
                    id=f"worker-{index}",
                    host=worker.host,
                    role=WORKER_ROLE,
                    vm_label=f"worker-{index}",
                )
            )
        return nodes

    @property
    def allowed_node_ids(self) -> set[str]:
        return {node.id for node in self.configured_hardware_nodes}

    def resolve_vm_label(self, node_id: str) -> str | None:
        for node in self.configured_hardware_nodes:
            if node.id == node_id:
                return node.vm_label
        return None

    def resolve_node(self, node_id: str) -> NodeTarget | None:
        for node in self.configured_hardware_nodes:
            if node.id != node_id:
                continue
            host = node.host
            return NodeTarget(
                id=node.id,
                host=host,
                vm_label=node.vm_label,
                node_exporter_url=f"http://{host}:{self.NODE_EXPORTER_PORT}",
                npu_exporter_url=f"http://{host}:{self.NPU_EXPORTER_PORT}",
            )
        return None

    @field_validator("WORKER_NODES", mode="before")
    @classmethod
    def _coerce_worker_nodes(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value)

    # ── 注册中心后端 (选填；未配置时智能体监控功能不可用) ──
    AGENT_REGISTER_URL: str = ""

    @property
    def agent_register_enabled(self) -> bool:
        """注册中心后端是否已配置。"""
        return bool(self.AGENT_REGISTER_URL.strip())

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
