from .db import get_db
from .repositories import UserRepository, OrderRepository


def __getattr__(name: str):
    if name in ("engine", "SessionLocal"):
        from . import db as _db

        return getattr(_db, name)
    raise AttributeError(name)


__all__ = ["engine", "SessionLocal", "get_db", "UserRepository", "OrderRepository"]
