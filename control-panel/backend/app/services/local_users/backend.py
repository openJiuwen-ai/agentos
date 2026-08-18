"""LocalUsersBackend — implements AbstractUserBackend with pure SQLAlchemy."""

import logging
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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
    """递归地将用户家目录的所有权和权限，使用 AGENTOS_SYS_UID/GID。"""
    path = _home_path(username)
    uid = settings.AGENTOS_SYS_UID
    gid = settings.AGENTOS_SYS_GID
    for dirpath, _, filenames in os.walk(str(path)):
        os.chown(dirpath, uid, gid, follow_symlinks=False)
        for fn in filenames:
            fp = os.path.join(dirpath, fn)
            os.chown(fp, uid, gid, follow_symlinks=False)


def _remove_home(username: str) -> None:
    path = _home_path(username)
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


def _derive_api_base() -> str:
    """从 LITELLM_ADMIN_URL 推导九问 config.yaml 中的 api_base。"""
    parsed = urlparse(settings.LITELLM_ADMIN_URL)
    return f"{parsed.scheme}://{parsed.netloc}/v1"


def _load_config_yaml(config_path: Path):
    """加载 config.yaml，返回 ruamel YAML 对象。"""
    from ruamel.yaml import YAML

    ryaml = YAML()
    ryaml.preserve_quotes = True
    return ryaml, ryaml.load(config_path.read_text(encoding="utf-8"))


def _save_config_yaml(config_path: Path, ryaml, data) -> None:
    """保存 config.yaml。"""
    import io

    buf = io.StringIO()
    ryaml.dump(data, buf)
    config_path.write_text(buf.getvalue(), encoding="utf-8")
    try:
        config_path.chmod(0o600)
    except OSError:
        pass


def _build_agentos_entry(
    api_base: str, api_key: str, model_name: str, context_window: int | None
) -> dict:
    """构建单个 agentos 条目。"""
    return {
        "model_client_config": {
            "api_base": api_base,
            "api_key": api_key,
            "model_name": model_name,
            "client_provider": "OpenAI",
            "verify_ssl": True,
            "timeout": 1800,
        },
        "model_config_obj": {
            "temperature": 0.95,
            "max_tokens": context_window if context_window is not None else "",
        },
    }


def _append_agentos_entries(
    username: str,
    api_base: str,
    api_key: str,
    models: list[tuple[str, int | None]],
) -> None:
    """往 config.yaml 的 models.agentos 列表追加模型条目。

    追加前先清理同 api_key 的旧条目，防止重复。
    每个模型一条，max_tokens 用模型自己的 context_window。
    """
    config_path = _home_path(username) / ".jiuwenswarm" / "config" / "config.yaml"
    if not config_path.is_file():
        logger.warning("用户 %s 的 config.yaml 不存在，跳过追加", username)
        return

    ryaml, data = _load_config_yaml(config_path)
    if data is None:
        return

    models_data = data.get("models")
    if not isinstance(models_data, dict):
        return

    agentos = models_data.get("agentos")
    if agentos is None:
        agentos = []
        models_data["agentos"] = agentos

    # 先清理同 api_key 的旧条目
    new_list = [
        item for item in agentos
        if item.get("model_client_config", {}).get("api_key") != api_key
    ]
    agentos.clear()
    agentos.extend(new_list)

    # 追加新条目
    for model_name, context_window in models:
        agentos.append(_build_agentos_entry(api_base, api_key, model_name, context_window))

    _save_config_yaml(config_path, ryaml, data)


def _filter_models_by_context(models: list[tuple[str, int | None]]) -> list[tuple[str, int | None]]:
    """按 model_name 去重，保留 context_window 最大的（None 视为最小）。"""
    best: dict[str, int | None] = {}
    for name, ctx in models:
        if name not in best:
            best[name] = ctx
        elif ctx is not None and (best[name] is None or ctx > best[name]):
            best[name] = ctx
    return list(best.items())


async def _ensure_user_default_key(
    session: AsyncSession, uid: str, username: str
) -> str | None:
    """默认 Key 缺失时，经 LiteLLM 新建一条并设为默认。

    返回明文 Key；LiteLLM 服务不可用或申请失败返回 None（调用方跳过该用户）。
    注意：必须在调用方关闭 session 前 commit —— 每用户独立 session 关闭时会
    自动 rollback，不 commit 的话刚设的默认标记会丢失。
    """
    from app.models.user_default_key import UserDefaultKey
    from app.services import get_litellm_svc

    svc = get_litellm_svc()
    if svc is None:
        logger.warning("LiteLLM 服务不可用，无法为用户 %s 新建默认 Key", username)
        return None

    try:
        key_info = await svc.apply_key(
            session, uid=uid, model=None, key_name="default-key"
        )
    except Exception:
        logger.warning("为用户 %s 新建默认 Key 失败", username, exc_info=True)
        return None

    key_id = key_info.get("key_id")
    if key_id:
        await UserDefaultKey.set_default(session, uid, key_id)
    await session.commit()
    return key_info.get("key")


async def _rebuild_user_agentos(session, username: str, filtered_models: list[tuple[str, int | None]]) -> None:
    """单用户全量重建 agentos：从 DB 查默认 Key，用最新模型列表整体替换。

    不从 config.yaml 读旧数据，每次都从 DB 拿最新 Key + 最新模型列表整体写入。
    """
    from app.models.litellm_user_key import LitellmUserKey
    from app.models.user_default_key import UserDefaultKey
    from app.services.litellm_service import decrypt_key

    # 从 DB 查用户
    user = await _get_user_by_username(session, username)
    if not user:
        return
    uid = str(user.id)

    # 查默认 Key（key_id 即 litellm_user_key.id）；缺失则经 LiteLLM 新建并设为默认
    default_row = await UserDefaultKey.get_by_uid(session, uid)
    api_key_plain = None
    if default_row and default_row.key_id:
        result = await session.execute(
            select(LitellmUserKey).where(LitellmUserKey.id == default_row.key_id)
        )
        key_record = result.scalars().first()
        if key_record:
            api_key_plain = decrypt_key(key_record.key)
    if not api_key_plain:
        api_key_plain = await _ensure_user_default_key(session, uid, username)
    if not api_key_plain:
        logger.warning(
            "用户 %s agentos 重建跳过：无可用默认 Key（新建失败或 LiteLLM 不可用）",
            username,
        )
        return
    api_base = _derive_api_base()

    # 读 config.yaml
    config_path = _home_path(username) / ".jiuwenswarm" / "config" / "config.yaml"
    if not config_path.is_file():
        logger.warning("用户 %s agentos 重建跳过：config.yaml 不存在", username)
        return

    ryaml, data = _load_config_yaml(config_path)
    if data is None:
        logger.warning("用户 %s agentos 重建跳过：config.yaml 为空", username)
        return

    models_data = data.get("models")
    if not isinstance(models_data, dict):
        logger.warning("用户 %s agentos 重建跳过：config.yaml 缺少 models 配置", username)
        return

    # 整体替换 agentos
    agentos = models_data.get("agentos")
    if agentos is None:
        agentos = []
        models_data["agentos"] = agentos

    agentos.clear()
    for model_name, context_window in filtered_models:
        agentos.append(_build_agentos_entry(api_base, api_key_plain, model_name, context_window))

    _save_config_yaml(config_path, ryaml, data)


async def _sync_all_users_agentos() -> None:
    """后台任务：模型变更后全量重建所有用户的 agentos。

    每个用户使用独立 session 处理：单个用户重建失败时，其事务被回滚/关闭，
    不会把共享事务置为 abort，导致后续用户全部报 InFailedSQLTransactionError。
    """
    try:
        from app.database import async_session_maker
        from app.models.litellm_model_params import LitellmModelParams

        async with async_session_maker() as session:
            models = await LitellmModelParams.list_all_models_with_context(session)
            filtered_models = _filter_models_by_context(models)

            result = await session.execute(select(User.username))
            usernames = list(result.scalars().all())

        for username in usernames:
            try:
                async with async_session_maker() as session:
                    await _rebuild_user_agentos(session, username, filtered_models)
            except Exception:
                logger.warning("重建用户 %s agentos 失败", username, exc_info=True)

        logger.info("模型变更同步完成，已处理 %d 个用户", len(usernames))
    except Exception:
        logger.warning("模型变更同步 agentos 失败", exc_info=True)


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
        """启动时初始化管理员：建用户 → 同步 LiteLLM → _setup_user_key_and_config。

        强依赖 LiteLLM：同步失败直接 return。
        Key/目录/config 交给 _setup_user_key_and_config 统一处理。
        失败回滚删用户 + 阻断启动（没有管理员管理面无法运行）。
        """
        from app.services import get_litellm_svc
        from app.services.litellm_service import (
            LitellmUpstreamError, LitellmConnectionError,
            USER_ALREADY_EXISTS_STATUS_CODES,
        )

        async with self._session_maker() as session:
            # ① 查 DB 有没有 admin
            admin_username = _validate_username(settings.AGENTOS_ADMIN_USERNAME)
            admin = await _get_user_by_username(session, admin_username)
            if not admin:
                admin_user = User(
                    username=admin_username,
                    hashed_password=hash_password(settings.AGENTOS_ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                session.add(admin_user)
                await session.commit()
                await session.refresh(admin_user)
                admin = admin_user

            uid = str(admin.id)
            username = admin.username

            # ② 获取 LiteLLM 服务 + 同步管理员（强依赖，失败 return）
            svc = None
            try:
                svc = get_litellm_svc()
            except Exception:
                logger.warning("获取 LiteLLM 服务失败", exc_info=True)

            if svc is None:
                return

            try:
                await svc.create_user(uid=uid)
                logger.info("管理员已同步到 LiteLLM")
            except LitellmUpstreamError as e:
                if e.status_code in USER_ALREADY_EXISTS_STATUS_CODES:
                    logger.info("管理员在 LiteLLM 已存在，跳过")
                else:
                    logger.warning("LiteLLM 同步管理员失败: %s %s", e.status_code, e.detail)
                    return
            except LitellmConnectionError:
                logger.warning("LiteLLM 不可达，跳过同步")
                return
            except Exception:
                logger.warning("同步管理员到 LiteLLM 异常", exc_info=True)
                return

            # ③ Key + 目录 + config（复用 _setup_user_key_and_config）
            # admin 也用 rollback_on_failure=True：管理员也是九问用户，Key/config 失败时回滚删用户
            # 不 catch：异常穿透 lifespan 阻断启动（没有管理员管理面无法运行）
            await self._setup_user_key_and_config(
                session, svc, uid, username, rollback_on_failure=True
            )

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
            # Step 1. 查重
            existing = await _get_user_by_username(session, username)
            if existing:
                raise ValueError("USERNAME_ALREADY_EXISTS")

            # Step 2. 入库 commit
            generated = None
            if password is None:
                password = generate_random_password()
                generated = password
            user = User(username=username, hashed_password=hash_password(password))
            session.add(user)
            await session.commit()
            await session.refresh(user)
            record = self._to_record(user)

            # Step 3. 创建 LiteLLM 用户（400/409=已存在跳过，其他失败回滚用户）
            uid = str(user.id)
            svc = None
            try:
                from app.services import get_litellm_svc
                from app.services.litellm_service import (
                    LitellmUpstreamError, LitellmConnectionError,
                    USER_ALREADY_EXISTS_STATUS_CODES,
                )

                svc = get_litellm_svc()
                if svc is not None:
                    await svc.create_user(uid=uid)
            except LitellmUpstreamError as e:
                if e.status_code in USER_ALREADY_EXISTS_STATUS_CODES:
                    pass  # 已存在，继续
                else:
                    await self._rollback_user(session, uid, username)
                    raise ValueError(f"创建 LiteLLM 用户失败: {e.detail}") from e
            except Exception as e:
                await self._rollback_user(session, uid, username)
                raise ValueError(f"创建 LiteLLM 用户失败") from e

            # Step 4. 若家目录已存在（旧用户残留），先删除再从模板重建，避免旧数据污染
            home = _home_path(username)
            if home.is_dir():
                logger.warning("用户 %s 家目录已存在，删除后从模板重建", username)
                _remove_home(username)
                if home.is_dir():
                    logger.error("用户 %s 家目录删除失败，中止创建", username)
                    await self._rollback_user(session, uid, username)
                    raise ValueError(f"用户 {username} 家目录删除失败")

            # Step 5. 申请 Key + 写 config（失败回滚用户）
            await self._setup_user_key_and_config(
                session, svc, uid, username, rollback_on_failure=True
            )

            return record, generated

    async def _setup_user_key_and_config(
        self, session, svc, uid: str, username: str, *, rollback_on_failure: bool = True
    ) -> dict:
        """为用户申请 Key 并写入九问 config.yaml。

        流程：查已有Key → 申请(如无) → 标记默认 → commit → 检查家目录 → 建目录 → 复制模板 → 写agentos → chown

        幂等：已有 Key 跳过申请；目录已存在跳过模板复制；config.yaml 缺失只补 config.yaml。

        Args:
            session: 数据库会话
            svc: LiteLLM 服务实例
            uid: 用户 ID
            username: 用户名
            rollback_on_failure: 失败时是否回滚用户（普通用户和管理员都 True）

        Returns:
            成功返回 {"key": 明文key}，失败时 _rollback_user + raise
        """
        from app.models.litellm_model_params import LitellmModelParams
        from app.models.litellm_user_key import LitellmUserKey
        from app.models.user_default_key import UserDefaultKey
        from app.services.litellm_service import decrypt_key

        try:
            # ① 查已有 Key
            existing_keys = await LitellmUserKey.list_by_uid(session, uid)
            if existing_keys:
                key_record = existing_keys[0]
                api_key_plain = decrypt_key(key_record.key)
                logger.info("用户 %s 已有 Key（alias=%s），跳过申请", username, key_record.key_alias)
                # 已有 Key 时不补默认标记，默认 Key 只在创建用户时申请的 Key 才标记
            else:
                # 无 Key，申请
                key_info = await self._apply_key(svc, session, uid, username)
                key_id = key_info.get("key_id")
                if key_id:
                    await UserDefaultKey.set_default(session, uid, key_id)
                await session.commit()
                api_key_plain = key_info.get("key", "")

            # ② 检查家目录 + config.yaml（不影响 ③，只管模板复制）
            home = _home_path(username)
            config_path = home / ".jiuwenswarm" / "config" / "config.yaml"
            if not home.is_dir():
                try:
                    _ensure_home(username)
                    _create_jwswarm_config(username)
                except Exception:
                    logger.warning("用户 %s 建家目录 / 复制模板失败", username, exc_info=True)
            elif not config_path.is_file():
                try:
                    src = Path(settings.AGENTOS_SWARM_TEMPLATE_DIR) / "config" / "config.yaml"
                    config_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src), str(config_path))
                except Exception:
                    logger.warning("用户 %s 补建 config.yaml 失败", username, exc_info=True)

            # ③ 写 agentos（有 Key 才写，无模型时写空列表）
            if api_key_plain:
                models = await LitellmModelParams.list_all_models_with_context(session)
                api_base = _derive_api_base()
                _append_agentos_entries(username, api_base, api_key_plain, models)

            # ④ chown
            _chown_home(username)

            return {"key": api_key_plain}
        except Exception as e:
            if rollback_on_failure:
                await self._rollback_user(session, uid, username)
                raise
            else:
                logger.warning("用户 %s 申请 Key / 写 config 失败", username, exc_info=True)
                return {}

    async def _apply_key(
        self, svc, session, uid: str, username: str
    ) -> dict:
        """申请 Key，model=None，失败回滚用户。"""
        if svc is None:
            raise RuntimeError(
                f"LiteLLM 服务不可用，无法为用户 {username} 申请 Key"
            )

        try:
            return await svc.apply_key(
                session, uid=uid, model=None, key_name="default-key"
            )
        except Exception as exc:
            await self._rollback_user(session, uid, username)
            raise RuntimeError(f"无法为用户 {username} 申请KEY") from exc

    async def _rollback_user(
        self, session: AsyncSession, uid: str, username: str
    ) -> None:
        """回滚用户创建：删家目录 + 删 LiteLLM 用户 + 删本地记录。每步 best-effort。"""
        try:
            await session.rollback()
        except Exception:
            logger.warning("回滚 session 失败", exc_info=True)

        try:
            _remove_home(username)
        except Exception as e:
            logger.warning("回滚时删除家目录失败: %s", e)

        try:
            from app.services import get_litellm_svc

            svc = get_litellm_svc()
            if svc is not None:
                async with self._session_maker() as rb_session:
                    await svc.delete_user(rb_session, uid=uid)
                    await rb_session.commit()
        except Exception:
            logger.warning("回滚时删除 LiteLLM 用户失败", exc_info=True)

        try:
            from app.models.user_default_key import UserDefaultKey

            async with self._session_maker() as rb_session:
                await UserDefaultKey.delete_by_uid(rb_session, uid)
                await rb_session.commit()
        except Exception:
            logger.warning("回滚时删除默认 Key 标记失败", exc_info=True)

        try:
            async with self._session_maker() as rb_session:
                user_obj = await _get_user_by_id(rb_session, uuid.UUID(uid))
                if user_obj:
                    await rb_session.delete(user_obj)
                    await rb_session.commit()
        except Exception:
            logger.warning("回滚时删除用户记录失败", exc_info=True)

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
                    value = _validate_username(value)
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
                logger.warning("删除用户 %s 家目录异常: %s", user.username, e)
            if _home_path(user.username).is_dir():
                logger.warning("用户 %s 家目录删除失败，残留目录将保留", user.username)

            # ── 默认 Key 标记清理（best-effort，独立事务；先删子表避免 FK 冲突）──
            try:
                from app.models.user_default_key import UserDefaultKey

                async with self._session_maker() as key_session:
                    await UserDefaultKey.delete_by_uid(key_session, str(user.id))
                    await key_session.commit()
            except Exception:
                logger.warning(
                    "Failed to delete default key mark for %s",
                    user.username,
                    exc_info=True,
                )

            # ── LiteLLM 用户清理（best-effort，独立事务，避免污染主事务）──
            try:
                from app.services import get_litellm_svc

                svc = get_litellm_svc()
                if svc is not None:
                    async with self._session_maker() as ll_session:
                        await svc.delete_user(ll_session, uid=str(user.id))
                        await ll_session.commit()
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
