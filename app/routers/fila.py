from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_user
from app.db import get_db
from app.models import StatusTipo, Usuario
from app.services import fila as fila_service
from app.templating import templates

router = APIRouter()


@router.get("/fila/fragment", response_class=HTMLResponse)
async def fila_fragment(
    request: Request, user: Usuario = Depends(require_user), db: AsyncSession = Depends(get_db)
):
    colaboradores = await fila_service.listar_fila(db)
    return templates.TemplateResponse(
        request,
        "partials/fila_fragment.html",
        {"colaboradores": colaboradores, "user": user, "StatusTipo": StatusTipo},
    )


@router.post("/fila/entrar")
async def entrar_na_fila(user: Usuario = Depends(require_user), db: AsyncSession = Depends(get_db)):
    await fila_service.entrar_na_fila(db, user)
    return RedirectResponse("/", status_code=303)


@router.post("/fila/sair")
async def sair_da_fila(user: Usuario = Depends(require_user), db: AsyncSession = Depends(get_db)):
    await fila_service.sair_da_fila(db, user)
    return RedirectResponse("/", status_code=303)


@router.post("/bastao/transferir")
async def bastao_transferir(user: Usuario = Depends(require_user), db: AsyncSession = Depends(get_db)):
    await fila_service.transferir_bastao(db)
    return RedirectResponse("/", status_code=303)


@router.post("/bastao/pular")
async def bastao_pular(user: Usuario = Depends(require_user), db: AsyncSession = Depends(get_db)):
    await fila_service.pular_bastao(db)
    return RedirectResponse("/", status_code=303)


@router.post("/status/atualizar")
async def status_atualizar(
    status_tipo: str = Form(...),
    detalhe: str | None = Form(None),
    user: Usuario = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    await fila_service.atualizar_status(db, user, StatusTipo(status_tipo), detalhe or None)
    return RedirectResponse("/", status_code=303)
