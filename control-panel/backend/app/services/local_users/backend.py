"""LocalUsersBackend — implements AbstractUserBackend with pure SQLAlchemy."""

import logging
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.config import settings
from app.schemas.user import PaginatedUsers, UserCredentials, UserRecord
from app.services.base import AbstractUserBackend
from app.services.local_users.password import (
    generate_random_password,
    hash_password,
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


def _create_home(username: str) -> None:
    path = _home_path(username)
    if path.exists():
        raise ValueError("HOME_ALREADY_EXISTS")
    path.mkdir(parents=True, mode=0o700)


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
                _create_home(settings.AGENTOS_ADMIN_USERNAME)
            except ValueError as e:
                logger.warning("Failed to create home directory for admin user: %s", e)

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

    async def list_users(self, page=1, page_size=20, sort="created_at", order="desc", search=None) -> PaginatedUsers:
        async with self._session_maker() as session:
            sort_col = getattr(User, sort, User.created_at)
            order_clause = sort_col.desc() if order == "desc" else sort_col.asc()

            base_query = select(User)
            if search:
                base_query = base_query.where(User.username.ilike(f"%{search}%"))

            total = (await session.execute(select(func.count()).select_from(base_query.subquery()))).scalar()
            result = await session.execute(
                base_query.order_by(order_clause).offset((page - 1) * page_size).limit(page_size)
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
                _create_home(username)
            except ValueError as e:
                if "HOME_ALREADY_EXISTS" in str(e):
                    raise ValueError("HOME_ALREADY_EXISTS") from e
                raise

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
            valid, new_hash = verify_password(old_password, user.hashed_password)
            if not valid:
                raise ValueError("原密码错误")
            if len(new_password) < 8:
                raise ValueError("新密码长度至少 8 位")
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
