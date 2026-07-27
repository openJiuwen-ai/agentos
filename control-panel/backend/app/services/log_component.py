import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log import LogComponent
from app.schemas.log import LogComponentCreate, LogComponentUpdate


async def get_all_components(
    session: AsyncSession, category: str | None = None,
) -> Sequence[LogComponent]:
    stmt = select(LogComponent)
    if category:
        stmt = stmt.where(LogComponent.category == category)
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_component_by_id(
    session: AsyncSession, component_id: uuid.UUID
) -> LogComponent | None:
    result = await session.execute(
        select(LogComponent).where(LogComponent.id == component_id)
    )
    return result.scalars().first()


async def get_component_by_name(
    session: AsyncSession, category: str, name: str
) -> LogComponent | None:
    result = await session.execute(
        select(LogComponent).where(
            LogComponent.category == category, LogComponent.name == name
        )
    )
    return result.scalars().first()


async def create_component(
    session: AsyncSession, data: LogComponentCreate
) -> LogComponent:
    component = LogComponent(
        category=data.category,
        name=data.name,
        log_path=data.log_path,
        description=data.description,
    )
    session.add(component)
    await session.flush()
    return component


async def update_component(
    session: AsyncSession,
    component_id: uuid.UUID,
    data: LogComponentUpdate,
) -> LogComponent | None:
    component = await get_component_by_id(session, component_id)
    if not component:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(component, key, value)
    await session.flush()
    return component


async def delete_component(
    session: AsyncSession, component_id: uuid.UUID
) -> bool:
    component = await get_component_by_id(session, component_id)
    if not component:
        return False
    await session.delete(component)
    await session.flush()
    return True


async def get_category_counts(
    session: AsyncSession,
) -> dict[str, int]:
    from sqlalchemy import func as sqlfunc

    result = await session.execute(
        select(LogComponent.category, sqlfunc.count(LogComponent.id))
        .group_by(LogComponent.category)
    )
    return {row[0]: row[1] for row in result.all()}
