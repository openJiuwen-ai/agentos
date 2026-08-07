"""LitellmModelParams ORM — 模型扩展参数表"""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, JSON, case, literal_column, select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


@dataclass
class LocalModelExtension:
    """模型本地扩展字段 — 收敛 create/update 的可选参数。"""

    instance_url: str | None = None
    max_concurrent: int | None = None
    extra_params: dict | None = None
    inference_engine: str | None = None


class LitellmModelParams(Base):
    __tablename__ = "litellm_model_params"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    instance_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    max_concurrent: Mapped[int | None] = mapped_column(nullable=True)
    extra_params: Mapped[dict | None] = mapped_column(JSON, default={}, nullable=True)
    inference_engine: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @staticmethod
    async def get_by_names(
        db: AsyncSession,
        model_names: list[str],
    ) -> dict[str, list["LitellmModelParams"]]:
        """按名称查询，返回 {model_name: [记录...]}，允许同名多条。"""
        if not model_names:
            return {}
        result = await db.execute(
            select(LitellmModelParams).where(
                LitellmModelParams.model_name.in_(model_names),
            )
        )
        rows = result.scalars().all()
        grouped: dict[str, list["LitellmModelParams"]] = {}
        for r in rows:
            grouped.setdefault(r.model_name, []).append(r)
        return grouped

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        model_id: str,
    ) -> "LitellmModelParams | None":
        """按 ID 查询单条记录。"""
        result = await db.execute(
            select(LitellmModelParams).where(LitellmModelParams.id == model_id)
        )
        return result.scalars().one_or_none()

    @staticmethod
    async def get_first_model_name(db: AsyncSession) -> str | None:
        result = await db.execute(
            select(LitellmModelParams.model_name)
            .order_by(LitellmModelParams.created_at)
            .limit(1)
        )
        return result.scalar()

    @staticmethod
    async def upsert(
        db: AsyncSession,
        model_id: str,
        model_name: str,
        ext: LocalModelExtension | None = None,
    ) -> "LitellmModelParams":
        """原子 upsert — INSERT ... ON CONFLICT (id) DO UPDATE。

        None 语义：保留已有值；空串与非空值：覆盖写入。
        """
        ext = ext or LocalModelExtension()
        now = datetime.now(timezone.utc)
        _ex_url = literal_column("excluded.instance_url")
        _ex_mc = literal_column("excluded.max_concurrent")
        _ex_extra = literal_column("excluded.extra_params")
        _ex_engine = literal_column("excluded.inference_engine")

        stmt = pg_insert(LitellmModelParams).values(
            id=model_id,
            model_name=model_name,
            instance_url=ext.instance_url,
            max_concurrent=ext.max_concurrent,
            extra_params=ext.extra_params,
            inference_engine=ext.inference_engine,
            created_at=now,
            updated_at=now,
        )
        _ex_name = literal_column("excluded.model_name")
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "model_name": case(
                    (_ex_name.isnot(None), _ex_name),
                    else_=LitellmModelParams.model_name,
                ),
                "instance_url": case(
                    (_ex_url.isnot(None), _ex_url),
                    else_=LitellmModelParams.instance_url,
                ),
                "max_concurrent": case(
                    (_ex_mc.isnot(None), _ex_mc),
                    else_=LitellmModelParams.max_concurrent,
                ),
                "extra_params": case(
                    (_ex_extra.isnot(None), _ex_extra),
                    else_=LitellmModelParams.extra_params,
                ),
                "inference_engine": case(
                    (_ex_engine.isnot(None), _ex_engine),
                    else_=LitellmModelParams.inference_engine,
                ),
                "updated_at": now,
            },
        )
        await db.execute(stmt)
        await db.flush()
        # Expire cached objects to force re-read from DB
        db.expire_all()
        return (
            (
                await db.execute(
                    select(LitellmModelParams).where(LitellmModelParams.id == model_id)
                )
            )
            .scalars()
            .one()
        )

    @staticmethod
    async def delete_by_id(db: AsyncSession, model_id: str) -> bool:
        result = await db.execute(
            delete(LitellmModelParams).where(LitellmModelParams.id == model_id)
        )
        await db.flush()
        return result.rowcount > 0

    @staticmethod
    async def delete_by_name(db: AsyncSession, model_name: str) -> int:
        """按名称删除，返回删除行数（同名可能多条）。"""
        result = await db.execute(
            delete(LitellmModelParams).where(
                LitellmModelParams.model_name == model_name,
            )
        )
        await db.flush()
        return result.rowcount

    @staticmethod
    async def count_by_grafana_job(
        db: AsyncSession,
        job: str,
        exclude_id: str | None = None,
    ) -> int:
        """统计引用了指定 grafana_job_name 的模型数（可排除当前模型）。

        使用 Python 层过滤以兼容 SQLite（测试）和 PostgreSQL（生产），
        避免 .astext / JSON_QUOTE 等方言特定行为。
        """
        stmt = select(LitellmModelParams.id, LitellmModelParams.extra_params)
        if exclude_id:
            stmt = stmt.where(LitellmModelParams.id != exclude_id)
        result = await db.execute(stmt)
        count = 0
        for _id, extra in result.all():
            if extra and extra.get("grafana_job_name") == job:
                count += 1
        return count
