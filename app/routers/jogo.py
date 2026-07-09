from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_user
from app.db import get_db
from app.models import Usuario
from app.services import jogo as jogo_service
from app.templating import templates

router = APIRouter()


@router.get("/jogo/simon", response_class=HTMLResponse)
async def jogo_simon(
    request: Request, user: Usuario = Depends(require_user), db: AsyncSession = Depends(get_db)
):
    ranking = await jogo_service.ranking_top5(db)
    return templates.TemplateResponse(request, "jogo_simon.html", {"user": user, "ranking": ranking})


@router.post("/jogo/simon/score")
async def jogo_simon_score(
    score: int = Form(...), user: Usuario = Depends(require_user), db: AsyncSession = Depends(get_db)
):
    await jogo_service.registrar_score(db, user, score)
    return {"ok": True}
