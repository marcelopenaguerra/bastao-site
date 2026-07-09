"""Cria um usuário admin local para testes manuais (não usar em produção)."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth.security import hash_password
from app.db import SessionLocal
from app.models import Usuario


async def main() -> None:
    async with SessionLocal() as db:
        db.add(
            Usuario(
                username="admin",
                nome="Administrador Teste",
                senha_hash=hash_password("senha-teste-123"),
                is_admin=True,
                must_change_password=False,
            )
        )
        await db.commit()
    print("Usuário 'admin' / 'senha-teste-123' criado.")


if __name__ == "__main__":
    asyncio.run(main())
