import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_user
from app.auth.routes import router as auth_router
from app.db import get_db
from app.models import StatusTipo, Usuario
from app.routers.admin import router as admin_router
from app.routers.demandas import router as demandas_router
from app.routers.fila import router as fila_router
from app.routers.jogo import router as jogo_router
from app.routers.relatorios import router as relatorios_router
from app.services import fila as fila_service
from app.services.timeouts import loop_timeouts
from app.templating import templates


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(loop_timeouts())
    yield
    task.cancel()


app = FastAPI(title="Bastão - Informática", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="app/static", check_dir=False), name="static")
app.include_router(auth_router)
app.include_router(fila_router)
app.include_router(demandas_router)
app.include_router(relatorios_router)
app.include_router(admin_router)
app.include_router(jogo_router)


@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request, user: Usuario = Depends(require_user), db: AsyncSession = Depends(get_db)
):
    colaboradores = await fila_service.listar_fila(db)
    return templates.TemplateResponse(
        request, "dashboard.html", {"user": user, "colaboradores": colaboradores, "StatusTipo": StatusTipo}
    )
