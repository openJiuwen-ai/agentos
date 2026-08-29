"""Static contract tests for the base/agent Dockerfile responsibility split."""

from pathlib import Path

_IMAGE_PROCESS_DIR = Path(__file__).resolve().parent.parent
_BASE_DOCKERFILE = _IMAGE_PROCESS_DIR / "base.Dockerfile"


class TestBaseDockerfileContract:
    @staticmethod
    def test_base_is_system_plus_scaffolding():
        content = _BASE_DOCKERFILE.read_text(encoding="utf-8")
        # 无用户层
        assert "groupadd" not in content
        assert "useradd" not in content
        assert "USER agentos" not in content
        # 有脚手架与 runtime 标识
        assert 'ENTRYPOINT ["/entrypoint.sh"]' in content
        assert 'CMD ["sleep", "infinity"]' in content
        assert "agentos.runtime_spec" in content
        assert "sshd_config" in content
        assert "openyuanrong_sdk" in content
        assert "agent_dx_executor" in content


_AGENT_DOCKERFILE = _IMAGE_PROCESS_DIR / "agent.Dockerfile"


class TestAgentDockerfileContract:
    @staticmethod
    def test_agent_owns_user_and_package_install():
        content = _AGENT_DOCKERFILE.read_text(encoding="utf-8")
        # 用户与归属权
        assert "ARG AGENTOS_SYS_UID=1000" in content
        assert "ARG AGENTOS_SYS_GID=1000" in content
        assert "groupadd -g ${AGENTOS_SYS_GID} agentos" in content
        assert "useradd -m agentos -u ${AGENTOS_SYS_UID} -g agentos" in content
        assert "chown -R agentos:agentos" in content
        assert "COPY --chown=agentos:agentos" in content
        assert "USER agentos" in content
        # 顺序：用户创建先于 COPY（用户名需可解析）
        assert content.index("useradd -m agentos") < content.index(
            "COPY --chown=agentos:agentos"
        )
        # 脚手架与 runtime 标识不在 agent
        assert "ENTRYPOINT" not in content
        assert "CMD" not in content
        assert "agentos.runtime_spec" not in content
        assert "sshd_config" not in content
