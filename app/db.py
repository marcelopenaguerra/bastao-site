from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

_connect_args = {}
if settings.database_url.startswith("postgresql"):
    # Supabase roda o pooler em modo "transaction" (pgbouncer) — nesse modo,
    # cada statement pode ir para uma conexão física diferente do Postgres,
    # então o cache de prepared statements do asyncpg precisa ficar desligado.
    _connect_args = {"statement_cache_size": 0}

engine = create_async_engine(settings.database_url, pool_pre_ping=True, connect_args=_connect_args)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
