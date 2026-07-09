"""Cria o primeiro usuário admin em produção (idempotente).

Uso (via Render Shell, ou localmente com DATABASE_URL apontando pra produção):
    python scripts/criar_primeiro_admin.py <username> <nome completo>

Gera uma senha temporária aleatória, imprime no terminal (não é salva em
lugar nenhum) e força a troca no primeiro login.
"""

import asyncio
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.auth.security import hash_password
from app.db import SessionLocal
from app.models import Usuario


async def main(username: str, nome: str) -> None:
    async with SessionLocal() as db:
        existente = (
            await db.execute(select(Usuario).where(Usuario.username == username))
        ).scalar_one_or_none()
        if existente is not None:
            print(f"Usuário '{username}' já existe — nada foi criado.")
            return

        senha_temporaria = secrets.token_urlsafe(9)
        db.add(
            Usuario(
                username=username,
                nome=nome,
                senha_hash=hash_password(senha_temporaria),
                is_admin=True,
                must_change_password=True,
            )
        )
        await db.commit()

    print(f"Admin criado: username='{username}', senha temporária='{senha_temporaria}'")
    print("Troca de senha será exigida no primeiro login.")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python scripts/criar_primeiro_admin.py <username> <nome completo>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1], " ".join(sys.argv[2:])))
