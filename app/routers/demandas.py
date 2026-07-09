from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_user
from app.db import get_db
from app.models import StatusColaborador, StatusTipo, Usuario
from app.services import demandas as demandas_service
from app.templating import templates

router = APIRouter()


@router.get("/demandas", response_class=HTMLResponse)
async def listar(request: Request, user: Usuario = Depends(require_user), db: AsyncSession = Depends(get_db)):
    demandas = await demandas_service.listar_demandas_ativas(db)
    status = await db.get(StatusColaborador, user.id)
    em_demanda = status is not None and status.status_tipo == StatusTipo.em_demanda
    return templates.TemplateResponse(
        request,
        "demandas.html",
        {"user": user, "demandas": demandas, "em_demanda": em_demanda, "status": status},
    )


@router.post("/demandas")
async def criar(
    texto: str = Form(...),
    prioridade: str = Form(...),
    setor: str | None = Form(None),
    user: Usuario = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    await demandas_service.criar_demanda(db, user, texto, prioridade, setor or None)
    return RedirectResponse("/demandas", status_code=303)


@router.post("/demandas/{demanda_id}/encerrar")
async def encerrar(
    demanda_id: int, user: Usuario = Depends(require_user), db: AsyncSession = Depends(get_db)
):
    await demandas_service.encerrar_demanda(db, demanda_id)
    return RedirectResponse("/demandas", status_code=303)


@router.post("/atividades/iniciar")
async def iniciar_atividade(
    atividade_texto: str = Form(...),
    demanda_id: int | None = Form(None),
    user: Usuario = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    await demandas_service.iniciar_atividade(db, user, atividade_texto, demanda_id)
    return RedirectResponse("/demandas", status_code=303)


@router.post("/atividades/finalizar")
async def finalizar_atividade(user: Usuario = Depends(require_user), db: AsyncSession = Depends(get_db)):
    await demandas_service.finalizar_atividade(db, user)
    return RedirectResponse("/demandas", status_code=303)
