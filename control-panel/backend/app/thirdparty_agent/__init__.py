"""Third-party agent module — table lifecycle management."""


def ensure_thirdparty_agent_tables(engine):
    """Lazy import to avoid requiring sqlalchemy at module load time."""
    from app.thirdparty_agent.engine import (  # noqa: F811
        ensure_thirdparty_agent_tables as _ensure)
    return _ensure(engine)


__all__ = ["ensure_thirdparty_agent_tables"]
