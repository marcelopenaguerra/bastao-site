from datetime import timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_user
from app.auth.security import (
    SESSION_COOKIE_NAME,
    generate_session_token,
    hash_password,
    hash_token,
    new_expiration,
    now_utc,
    verify_password,
)
from app.config import settings
from app.db import get_db
from app.models import Sessao, TentativaLogin, Usuario
from app.templating import templates

router = APIRouter()

LOGIN_ATTEMPT_LIMIT = 5
LOGIN_ATTEMPT_WINDOW = timedelta(minutes=5)


async def _tentativas_recentes(db: AsyncSession, identificador: str) -> int:
    limite = now_utc() - LOGIN_ATTEMPT_WINDOW
    result = await db.execute(
        select(func.count()).select_from(TentativaLogin).where(
            TentativaLogin.username_tentado == identificador,
            TentativaLogin.sucesso.is_(False),
            TentativaLogin.criado_em >= limite,
        )
    )
    return result.scalar_one()


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, user: Usuario | None = Depends(get_current_user)):
    if user is not None:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"erro": None})


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    identificador: str = Form(...),
    senha: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    identificador = identificador.strip()

    if await _tentativas_recentes(db, identificador) >= LOGIN_ATTEMPT_LIMIT:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"erro": "Muitas tentativas de login. Tente novamente em alguns minutos."},
            status_code=429,
        )

    result = await db.execute(
        select(Usuario).where(
            or_(Usuario.username == identificador, Usuario.nome == identificador),
            Usuario.ativo.is_(True),
        )
    )
    usuario = result.scalar_one_or_none()

    login_ok = usuario is not None and verify_password(senha, usuario.senha_hash)

    db.add(
        TentativaLogin(
            username_tentado=identificador,
            sucesso=login_ok,
            ip_origem=request.client.host if request.client else None,
        )
    )

    if not login_ok:
        await db.commit()
        return templates.TemplateResponse(
            request, "login.html", {"erro": "Usuário ou senha inválidos."}, status_code=401
        )

    token = generate_session_token()
    sessao = Sessao(
        usuario_id=usuario.id,
        token_hash=hash_token(token),
        expira_em=new_expiration(),
        ip_origem=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(sessao)
    await db.commit()

    destino = "/trocar-senha" if usuario.must_change_password else "/"
    response = RedirectResponse(destino, status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=int(timedelta(hours=8).total_seconds()),
    )
    return response


@router.post("/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        token_hash = hash_token(token)
        result = await db.execute(select(Sessao).where(Sessao.token_hash == token_hash))
        sessao = result.scalar_one_or_none()
        if sessao is not None:
            sessao.revogado_em = now_utc()
            await db.commit()

    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.get("/trocar-senha", response_class=HTMLResponse)
async def trocar_senha_form(request: Request, user: Usuario = Depends(require_user)):
    return templates.TemplateResponse(request, "trocar_senha.html", {"erro": None})


@router.post("/trocar-senha", response_class=HTMLResponse)
async def trocar_senha_submit(
    request: Request,
    nova_senha: str = Form(...),
    confirmar_senha: str = Form(...),
    user: Usuario = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    if len(nova_senha) < 8:
        return templates.TemplateResponse(
            request, "trocar_senha.html", {"erro": "A senha deve ter ao menos 8 caracteres."}, status_code=400
        )
    if nova_senha != confirmar_senha:
        return templates.TemplateResponse(
            request, "trocar_senha.html", {"erro": "As senhas não coincidem."}, status_code=400
        )

    usuario_db = await db.get(Usuario, user.id)
    usuario_db.senha_hash = hash_password(nova_senha)
    usuario_db.must_change_password = False
    await db.commit()

    return RedirectResponse("/", status_code=303)
