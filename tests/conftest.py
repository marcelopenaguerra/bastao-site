import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["ENV"] = "local"

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.auth.security import hash_password
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Usuario


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db():
    async with SessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def criar_usuario(
    db, username: str, nome: str, senha: str = "senha-teste-123", is_admin: bool = False
) -> Usuario:
    usuario = Usuario(
        username=username,
        nome=nome,
        senha_hash=hash_password(senha),
        is_admin=is_admin,
        must_change_password=False,
    )
    db.add(usuario)
    await db.commit()
    await db.refresh(usuario)
    return usuario
