# AgentOS Panel — Backend API

基于 FastAPI 的用户管理后端，为 AgentOS 控制面板提供认证、用户 CRUD 和权限基础设施。

## 技术栈

- **Python 3.11+**
- **FastAPI** — 异步 Web 框架
- **SQLAlchemy 2.0 (async)** + **asyncpg** — 异步 PostgreSQL 驱动
- **Pydantic Settings** — 环境变量配置管理
- **pwdlib** — Argon2 / bcrypt 密码哈希
- **python-jose** — JWT 签发与校验

## 项目结构

```
backend/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置类（环境变量）
│   ├── database.py          # 数据库引擎 & session
│   ├── api/v1/              # HTTP 路由
│   ├── iam/                 # IAM 鉴权（JWT、权限）
│   ├── models/              # ORM 模型
│   ├── schemas/             # 请求/响应模型
│   ├── services/            # 可插拔用户系统后端
│   └── core/                # 日志等核心模块
├── tests/
├── .env.example
└── pyproject.toml
```

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

启动后会自动：
1. 初始化数据库引擎
2. 创建用户表 + IAM 表
3. 种子初始 admin 用户

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | (必填) | PostgreSQL 连接串（asyncpg） |
| `AGENTOS_ADMIN_USERNAME` | (必填) | 初始管理员用户名 |
| `AGENTOS_ADMIN_PASSWORD` | (必填) | 初始管理员密码 |
| `USER_SYSTEM_BACKEND` | `local-users` | 用户系统后端类型 |
| `AGENTOS_HOME_BASE` | `/home/agentos/users` | 用户 home 目录基础路径 |
| `JWT_SECRET_KEY` | `change-me-in-production` | JWT 签名密钥 |
| `JWT_ALGORITHM` | `HS256` | JWT 签名算法 |
| `JWT_ACCESS_EXPIRE_MINUTES` | `15` | access_token 有效期（分钟） |
| `JWT_REFRESH_EXPIRE_DAYS` | `7` | refresh_token 有效期（天） |
| `LOG_DIR` | `/home/agentos/logs` | 日志文件目录 |
| `LOG_MAX_BYTES` | `10485760` (10 MB) | 单个日志文件最大字节数 |
| `LOG_BACKUP_COUNT` | `5` | 保留的历史日志文件数 |

> **Docker 部署**：以非 root 用户 `agentos` 运行时，确保 `AGENTOS_HOME_BASE` 和 `LOG_DIR` 均位于 `/home/agentos/` 下，避免权限问题。

## API 端点

### Auth

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| POST | `/api/v1/auth/login` | 无 | 用户名+密码登录，返回双 token |
| POST | `/api/v1/auth/refresh` | 无 | 用 refresh_token 换取新 token 对 |
| POST | `/api/v1/auth/logout` | Bearer | 吊销 refresh_token |
| POST | `/api/v1/auth/verify` | 无 | 校验 access_token 有效性 + 资源权限 |
| GET | `/api/v1/auth/permissions` | Bearer | 获取当前用户权限矩阵 |

### Users

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| GET | `/api/v1/users?page=&page_size=&sort=&order=&search=` | Bearer (admin) | 分页用户列表 |
| POST | `/api/v1/users/batch` | Bearer (admin) | 批量创建用户（自动生成密码） |
| GET | `/api/v1/users/me` | Bearer | 当前用户信息 |
| PUT | `/api/v1/users/me/password` | Bearer | 修改自己的密码 |
| PATCH | `/api/v1/users/{user_id}` | Bearer (admin) | 修改用户活跃状态（不能修改管理员账户） |
| DELETE | `/api/v1/users/{user_id}` | Bearer (admin) | 删除用户及 home 目录（不能删除管理员账户） |
| POST | `/api/v1/users/{user_id}/reset-password` | Bearer (admin) | 强制重置用户密码（不能重置管理员密码） |

### 通用

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 服务信息 |
| GET | `/health` | 健康检查 |

**统一响应格式**：`{"code": 200, "message": "success", "data": {...}}`
