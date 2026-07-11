# AgentOS Panel — Backend API

基于 FastAPI 的用户管理后端，为 AgentOS 控制面板提供认证、用户 CRUD 和权限基础设施。

## 技术栈

- **Python 3.11+**
- **FastAPI** — 异步 Web 框架
- **SQLAlchemy 2.0 (async)** + **asyncpg** — 异步 PostgreSQL 驱动
- **Pydantic Settings** — 环境变量配置管理
- **pwdlib** — Argon2 / bcrypt 密码哈希

## 项目结构

```
backend/
├── app/
│   ├── main.py            # FastAPI 入口，lifespan 管理
│   ├── config.py          # pydantic-settings 配置类
│   ├── database.py        # SQLAlchemy async engine & session
│   ├── core/              # 核心模块（预留）
│   ├── models/            # ORM 模型
│   │   └── base.py        # DeclarativeBase 基类
│   ├── schemas/           # Pydantic / dataclass DTO
│   │   └── user.py        # UserCredentials, UserRecord, PaginatedUsers
│   └── services/          # 可插拔用户系统后端
│       ├── base.py        # AbstractUserBackend 抽象接口
│       └── local_users/  # 内置本地用户后端（本地数据库）
│           ├── backend.py
│           ├── models.py
│           └── password.py
├── .env.example
└── pyproject.toml
```

## 架构设计

核心思路是 **可插拔的用户系统后端**。`AbstractUserBackend` 定义了用户 CRUD、密码验证、生命周期管理的统一接口，具体实现通过 `USER_SYSTEM_BACKEND` 环境变量切换。

当前内置实现：
- **local-users** — 基于本地 PostgreSQL 的完整用户管理（`app/services/local_users/`）

IAM 层（JWT 签发、权限校验、Token 撤销）与用户后端解耦，后端只负责用户数据的存储和验证（后续上库）

## 快速开始

```bash
# 1. 安装依赖
cd control-panel/backend
uv sync

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入实际的数据库连接信息

# 3. 启动服务
uvicorn app.main:app --reload
```

启动后会自动创建数据库表并 seed 初始 admin 用户。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `postgresql+asyncpg://agentos:agentos@localhost:5432/agentos_panel` | PostgreSQL 连接串 |
| `AGENTOS_ADMIN_USERNAME` | `admin` | 初始管理员用户名 |
| `AGENTOS_ADMIN_PASSWORD` | `admin123` | 初始管理员密码 |
| `USER_SYSTEM_BACKEND` | `local-users` | 用户系统后端类型 |
| `AGENTOS_HOME_BASE` | `/home` | 用户 home 目录基础路径 |

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 服务信息 |
| GET | `/health` | 健康检查 |

> 用户 CRUD、认证等完整接口由 IAM 层挂载，当前为最小化启动示例。

## 添加新后端

1. 在 `app/services/` 下创建新目录，实现 `AbstractUserBackend` 接口
2. 在 `app/services/__init__.py` 的 `_BACKEND_REGISTRY` 中注册
3. 将 `USER_SYSTEM_BACKEND` 设为新后端名称

```python
# 注册示例
register_backend("ldap", "app.services.ldap.LDAPBackend")
```
