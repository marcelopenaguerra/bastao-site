from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import SESSION_COOKIE_NAME, as_aware_utc, hash_token, now_utc
from app.db import get_db
from app.models import Sessao, Usuario


class RedirectToLogin(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})


class RedirectToTrocarSenha(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/trocar-senha"})


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> Usuario | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None

    token_hash = hash_token(token)
    result = await db.execute(
        select(Sessao).where(Sessao.token_hash == token_hash, Sessao.revogado_em.is_(None))
    )
    sessao = result.scalar_one_or_none()
    if sessao is None or as_aware_utc(sessao.expira_em) < now_utc():
        return None

    usuario = await db.get(Usuario, sessao.usuario_id)
    if usuario is None or not usuario.ativo:
        return None

    return usuario


ROTAS_ISENTAS_DE_TROCA_DE_SENHA = {"/trocar-senha", "/logout"}


async def require_user(request: Request, user: Usuario | None = Depends(get_current_user)) -> Usuario:
    if user is None:
        raise RedirectToLogin()
    if user.must_change_password and request.url.path not in ROTAS_ISENTAS_DE_TROCA_DE_SENHA:
        raise RedirectToTrocarSenha()
    return user


async def require_admin(user: Usuario = Depends(require_user)) -> Usuario:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito a administradores")
    return user
