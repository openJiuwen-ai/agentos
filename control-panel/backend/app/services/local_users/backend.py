"""LocalUsersBackend — implements AbstractUserBackend with pure SQLAlchemy."""

import logging
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.config import settings
from app.schemas.user import (
    ListUsersParams,
    PaginatedUsers,
    UserCredentials,
    UserRecord,
)
from app.services.base import AbstractUserBackend
from app.services.local_users.password import (
    generate_random_password,
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.services.local_users.models import User

logger = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────────────


def _validate_username(username: str) -> str:
    username = username.strip().lower()
    if not re.match(r"^[a-z0-9_-]{3,32}$", username):
        raise ValueError("用户名格式无效（3-32位小写字母/数字/下划线/连字符）")
    return username


def _home_path(username: str) -> Path:
    return Path(settings.AGENTOS_HOME_BASE) / username


def _ensure_home(username: str) -> None:
    """创建用户家目录；已存在则跳过。"""
    path = _home_path(username)
    path.mkdir(parents=True, mode=0o700, exist_ok=True)


def _copy_tree_overwrite(src: Path, dst: Path) -> None:
    """递归复制目录树，目标文件已存在时直接覆盖。"""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            _copy_tree_overwrite(item, target)
        else:
            shutil.copy2(str(item), str(target))


def _create_jwswarm_config(username: str) -> None:
    """从模板目录复制 .jiuwenswarm 到用户家目录；已有文件则完全覆盖，失败则清理。"""
    src = Path(settings.AGENTOS_SWARM_TEMPLATE_DIR)
    if not src.is_dir():
        logger.warning("swarm 模板目录 %s 不存在，跳过复制", src)
        return
    dst = _home_path(username) / ".jiuwenswarm"
    try:
        _copy_tree_overwrite(src, dst)
    except Exception:
        logger.exception("复制 .jiuwenswarm 模板到用户 %s 失败", username)
        shutil.rmtree(str(dst), ignore_errors=True)
        raise


def _chown_home(username: str) -> None:
    """递归地将用户家目录的所有权设为 uid=1000, gid=1000。"""
    path = _home_path(username)
    for dirpath, _, filenames in os.walk(str(path)):
        os.chown(dirpath, 1000, 1000)
        for fn in filenames:
            os.chown(os.path.join(dirpath, fn), 1000, 1000)


def _remove_home(username: str) -> None:
    path = _home_path(username)
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


async def _get_user_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def _get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


# ── Backend class ───────────────────────────────────────────────────


class LocalUsersBackend(AbstractUserBackend):
    """User-system backend with no framework dependencies.

    Uses the shared database engine from ``app.database`` — does not create
    its own connection pool.
    """

    def __init__(self) -> None:
        pass

    @property
    def _session_maker(self):
        import app.database as _db

        if _db.async_session_maker is None:
            raise RuntimeError(
                "database.init_engine() must be called before backend use"
            )
        return _db.async_session_maker

    @staticmethod
    def _to_record(u: User) -> UserRecord:
        return UserRecord(
            user_id=str(u.id),
            username=u.username,
            role=u.role,
            is_active=u.is_active,
            token_version=u.token_version,
            created_at=u.created_at,
        )

    @staticmethod
    def _to_credentials(u: User) -> UserCredentials:
        return UserCredentials(
            user_id=str(u.id),
            username=u.username,
            role=u.role,
            token_version=u.token_version,
            is_active=u.is_active,
        )

    # ── Lifecycle ───────────────────────────────────────────────────

    async def on_startup(self) -> None:
        import app.database as _db

        engine = _db.engine
        if engine is None:
            raise RuntimeError(
                "database.init_engine() must be called before backend.on_startup()"
            )
        async with engine.begin() as conn:
            await conn.run_sync(User.metadata.create_all)
        logger.info("LocalUsersBackend tables ensured on shared engine.")

    async def on_shutdown(self) -> None:
        pass  # engine lifecycle is owned by app.database

    def get_engine(self) -> AsyncEngine | None:
        import app.database as _db

        return _db.engine

    async def seed_initial_admin(self) -> None:
        async with self._session_maker() as session:
            existing = await _get_user_by_username(
                session, settings.AGENTOS_ADMIN_USERNAME
            )
            if existing:
                return
            admin = User(
                username=settings.AGENTOS_ADMIN_USERNAME,
                hashed_password=hash_password(settings.AGENTOS_ADMIN_PASSWORD),
                role="admin",
                is_active=True,
            )
            session.add(admin)
            await session.commit()
            try:
                _ensure_home(settings.AGENTOS_ADMIN_USERNAME)
                _chown_home(settings.AGENTOS_ADMIN_USERNAME)
            except OSError:
                logger.warning("Failed to create home directory for admin user", exc_info=True)

    # ── Authentication ──────────────────────────────────────────────

    async def authenticate(
        self, username: str, password: str
    ) -> UserCredentials | None:
        async with self._session_maker() as session:
            user = await _get_user_by_username(session, username)
            if user is None:
                hash_password(password)  # timing-attack defence
                return None
            valid, new_hash = verify_password(password, user.hashed_password)
            if not valid:
                return None
            if new_hash is not None:
                user.hashed_password = new_hash
                await session.commit()
            if not user.is_active:
                return None
            return self._to_credentials(user)

    # ── User CRUD ───────────────────────────────────────────────────

    async def get_user_by_id(self, user_id: uuid.UUID) -> UserRecord | None:
        async with self._session_maker() as session:
            user = await _get_user_by_id(session, user_id)
            return self._to_record(user) if user else None

    async def get_user_by_username(self, username: str) -> UserRecord | None:
        async with self._session_maker() as session:
            user = await _get_user_by_username(session, username)
            return self._to_record(user) if user else None

    async def list_users(self, params: ListUsersParams) -> PaginatedUsers:
        async with self._session_maker() as session:
            sort_col = getattr(User, params.sort, User.created_at)
            order_clause = (
                sort_col.desc() if params.order == "desc" else sort_col.asc()
            )

            base_query = select(User)
            if params.search:
                base_query = base_query.where(
                    User.username.ilike(f"%{params.search}%")
                )
            if params.role:
                base_query = base_query.where(User.role == params.role)
            if params.is_active is not None:
                base_query = base_query.where(User.is_active == params.is_active)

            total = (await session.execute(select(func.count()).select_from(base_query.subquery()))).scalar()
            result = await session.execute(
                base_query.order_by(order_clause)
                .offset((params.page - 1) * params.page_size)
                .limit(params.page_size)
            )
            return PaginatedUsers(
                items=[self._to_record(u) for u in result.scalars().all()],
                total=total,
            )

    async def create_user(
        self, username: str, password: str | None = None
    ) -> tuple[UserRecord, str | None]:
        username = _validate_username(username)
        async with self._session_maker() as session:
            existing = await _get_user_by_username(session, username)
            if existing:
                raise ValueError("USERNAME_ALREADY_EXISTS")
            try:
                _ensure_home(username)
            except OSError as e:
                raise ValueError("HOME_CREATE_FAILED") from e
            try:
                _create_jwswarm_config(username)
            except Exception as e:
                raise ValueError("SWARM_CONFIG_FAILED") from e
            _chown_home(username)

            generated = None
            if password is None:
                password = generate_random_password()
                generated = password
            user = User(username=username, hashed_password=hash_password(password))
            session.add(user)
            await session.commit()
            await session.refresh(user)

            # ── LiteLLM 用户同步（best-effort）──────────────────────────
            try:
                from app.services import get_litellm_svc

                svc = get_litellm_svc()
                if svc is not None:
                    await svc.create_user(uid=str(user.id))
            except Exception:
                logger.warning(
                    "Failed to create LiteLLM user for %s",
                    username,
                    exc_info=True,
                )

            return self._to_record(user), generated

    async def update_user(
        self, user_id: uuid.UUID, update_dict: dict[str, Any]
    ) -> UserRecord:
        async with self._session_maker() as session:
            user = await _get_user_by_id(session, user_id)
            if not user:
                raise ValueError("用户不存在或密码错误")
            allowed_fields = {"username", "password", "is_active", "role"}
            for field, value in update_dict.items():
                if field not in allowed_fields:
                    continue
                if field == "password" and value is not None:
                    user.hashed_password = hash_password(value)
                    user.token_version += 1
                elif field == "username" and value is not None:
                    ex = await _get_user_by_username(session, value)
                    if ex and ex.id != user.id:
                        raise ValueError("USERNAME_ALREADY_EXISTS")
                    user.username = value
                else:
                    setattr(user, field, value)
            await session.commit()
            await session.refresh(user)
            return self._to_record(user)

    async def delete_user(self, user_id: uuid.UUID) -> None:
        async with self._session_maker() as session:
            user = await _get_user_by_id(session, user_id)
            if not user:
                raise ValueError("用户不存在或密码错误")
            try:
                _remove_home(user.username)
            except Exception as e:
                logger.warning(
                    "Failed to remove home directory for user %s: %s", user.username, e
                )

            # ── LiteLLM 用户清理（best-effort，提前执行确保 session 仍可用）──
            try:
                from app.services import get_litellm_svc

                svc = get_litellm_svc()
                if svc is not None:
                    await svc.delete_user(session, uid=str(user.id))
            except Exception:
                logger.warning(
                    "Failed to delete LiteLLM user for %s",
                    user.username,
                    exc_info=True,
                )

            await session.delete(user)
            await session.commit()

    async def change_password(
        self, user_id: uuid.UUID, old_password: str, new_password: str
    ) -> None:
        async with self._session_maker() as session:
            user = await _get_user_by_id(session, user_id)
            if not user:
                raise ValueError("用户不存在或密码错误")

            # 1. Verify old password
            valid, new_hash = verify_password(old_password, user.hashed_password)
            if not valid:
                raise ValueError("原密码错误")

            # 2. Strength check
            strength_errors = validate_password_strength(
                new_password, user.username
            )
            if strength_errors:
                raise ValueError("；".join(strength_errors))

            # 3. Must not be same as current password
            same, _ = verify_password(new_password, user.hashed_password)
            if same:
                raise ValueError("新密码不能与当前密码相同")

            # 4. Store and bump version
            user.hashed_password = hash_password(new_password)
            user.token_version += 1
            await session.commit()

    async def reset_password(self, user_id: uuid.UUID) -> str:
        async with self._session_maker() as session:
            user = await _get_user_by_id(session, user_id)
            if not user:
                raise ValueError("用户不存在或密码错误")
            new_password = generate_random_password()
            user.hashed_password = hash_password(new_password)
            user.token_version += 1
            await session.commit()
            return new_password
