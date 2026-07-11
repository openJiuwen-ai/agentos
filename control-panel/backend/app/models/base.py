"""Shared SQLAlchemy DeclarativeBase — used by all models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
