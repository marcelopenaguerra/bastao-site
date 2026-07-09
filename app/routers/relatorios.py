import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_user
from app.db import get_db
from app.models import Usuario
from app.services import relatorios as relatorios_service
from app.templating import templates

router = APIRouter()


@router.get("/relatorios", response_class=HTMLResponse)
async def relatorios(
    request: Request,
    inicio: str | None = Query(None),
    fim: str | None = Query(None),
    user: Usuario = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    inicio_dt = datetime.fromisoformat(inicio) if inicio else None
    fim_dt = datetime.fromisoformat(fim) if fim else None

    ranking = await relatorios_service.ranking_bastao(db)
    atividades = await relatorios_service.resumo_atividades(db, inicio_dt, fim_dt)

    return templates.TemplateResponse(
        request,
        "relatorios.html",
        {
            "user": user,
            "ranking": ranking,
            "atividades": atividades,
            "formatar_tempo": relatorios_service.formatar_tempo,
            "inicio": inicio or "",
            "fim": fim or "",
        },
    )


@router.get("/relatorios/export.csv")
async def exportar_csv(user: Usuario = Depends(require_user), db: AsyncSession = Depends(get_db)):
    ranking = await relatorios_service.ranking_bastao(db)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["nome", "rodadas", "tempo_total_segundos"])
    for item in ranking:
        writer.writerow([item.usuario.nome, item.rodadas, item.tempo_total_segundos])
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=relatorio_bastao.csv"},
    )
