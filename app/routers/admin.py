import csv
import io
import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.db import get_db
from app.models import AtividadeLog, Demanda, Usuario
from app.services import admin as admin_service
from app.templating import templates

router = APIRouter()


@router.get("/admin", response_class=HTMLResponse)
async def admin_index(user: Usuario = Depends(require_admin)):
    return RedirectResponse("/admin/usuarios", status_code=303)


@router.get("/admin/usuarios", response_class=HTMLResponse)
async def admin_usuarios(
    request: Request,
    senha_gerada: str | None = None,
    user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    usuarios = await admin_service.listar_usuarios(db)
    return templates.TemplateResponse(
        request, "admin_usuarios.html", {"user": user, "usuarios": usuarios, "senha_gerada": senha_gerada}
    )


@router.post("/admin/usuarios")
async def admin_criar_usuario(
    username: str = Form(...),
    nome: str = Form(...),
    is_admin_novo: bool = Form(False),
    user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    _, senha_temporaria = await admin_service.criar_usuario(db, username, nome, is_admin_novo)
    return RedirectResponse(f"/admin/usuarios?senha_gerada={senha_temporaria}", status_code=303)


@router.post("/admin/usuarios/{usuario_id}/ativar")
async def admin_ativar(
    usuario_id: uuid.UUID, user: Usuario = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    await admin_service.alternar_ativo(db, usuario_id, True)
    return RedirectResponse("/admin/usuarios", status_code=303)


@router.post("/admin/usuarios/{usuario_id}/desativar")
async def admin_desativar(
    usuario_id: uuid.UUID, user: Usuario = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    await admin_service.alternar_ativo(db, usuario_id, False)
    return RedirectResponse("/admin/usuarios", status_code=303)


@router.post("/admin/usuarios/{usuario_id}/resetar-senha")
async def admin_resetar_senha(
    usuario_id: uuid.UUID, user: Usuario = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    senha_temporaria = await admin_service.resetar_senha(db, usuario_id)
    return RedirectResponse(f"/admin/usuarios?senha_gerada={senha_temporaria}", status_code=303)


@router.get("/admin/estatisticas", response_class=HTMLResponse)
async def admin_estatisticas(
    request: Request, user: Usuario = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    stats = await admin_service.estatisticas_gerais(db)
    return templates.TemplateResponse(request, "admin_estatisticas.html", {"user": user, "stats": stats})


@router.get("/admin/backup")
async def admin_backup(user: Usuario = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    usuarios = (await db.execute(select(Usuario))).scalars().all()
    demandas = (await db.execute(select(Demanda))).scalars().all()
    atividades = (await db.execute(select(AtividadeLog))).scalars().all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)

    writer.writerow(["=== usuarios ==="])
    writer.writerow(["username", "nome", "is_admin", "ativo"])
    for u in usuarios:
        writer.writerow([u.username, u.nome, u.is_admin, u.ativo])

    writer.writerow([])
    writer.writerow(["=== demandas ==="])
    writer.writerow(["id", "texto", "prioridade", "setor", "ativa", "criado_em"])
    for d in demandas:
        writer.writerow([d.id, d.texto, d.prioridade, d.setor, d.ativa, d.criado_em])

    writer.writerow([])
    writer.writerow(["=== atividades_log ==="])
    writer.writerow(["id", "usuario_id", "tipo", "atividade_texto", "duracao_minutos", "motivo", "criado_em"])
    for a in atividades:
        writer.writerow([a.id, a.usuario_id, a.tipo, a.atividade_texto, a.duracao_minutos, a.motivo, a.criado_em])

    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=backup_bastao.csv"},
    )


@router.get("/admin/sql", response_class=HTMLResponse)
async def admin_sql_form(request: Request, user: Usuario = Depends(require_admin)):
    return templates.TemplateResponse(
        request, "admin_sql.html", {"user": user, "consulta": "", "colunas": None, "linhas": None, "erro": None}
    )


@router.post("/admin/sql", response_class=HTMLResponse)
async def admin_sql_executar(
    request: Request,
    consulta: str = Form(...),
    user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    colunas, linhas, erro = None, None, None
    try:
        colunas, linhas = await admin_service.executar_select(db, consulta)
    except admin_service.ConsultaNaoPermitida as exc:
        erro = str(exc)

    return templates.TemplateResponse(
        request,
        "admin_sql.html",
        {"user": user, "consulta": consulta, "colunas": colunas, "linhas": linhas, "erro": erro},
    )
