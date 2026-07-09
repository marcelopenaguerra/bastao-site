from datetime import timedelta

from app.auth.security import now_utc
from app.models import AtividadeLog, EventoLog, StatusColaborador, StatusTipo
from app.services import demandas as demandas_service
from app.services import fila as fila_service
from app.services.timeouts import verificar_timeouts
from tests.conftest import criar_usuario


async def test_iniciar_e_finalizar_atividade_registra_log(db):
    joao = await criar_usuario(db, "joao", "João")
    demanda = await demandas_service.criar_demanda(db, joao, "Resetar senha", "alta")

    await demandas_service.iniciar_atividade(db, joao, "Atendendo chamado", demanda.id)

    status = await db.get(StatusColaborador, joao.id)
    assert status.status_tipo == StatusTipo.em_demanda
    assert status.demanda_atual_id == demanda.id

    await demandas_service.finalizar_atividade(db, joao)

    status = await db.get(StatusColaborador, joao.id)
    assert status.status_tipo == StatusTipo.na_fila
    assert status.demanda_atual_id is None

    from sqlalchemy import select

    logs = (await db.execute(select(AtividadeLog))).scalars().all()
    assert len(logs) == 1
    assert logs[0].demanda_id == demanda.id
    assert logs[0].tipo == "demanda"
    assert logs[0].motivo == "manual"


async def test_encerrar_demanda_marca_inativa(db):
    joao = await criar_usuario(db, "joao", "João")
    demanda = await demandas_service.criar_demanda(db, joao, "Trocar toner", "normal")

    await demandas_service.encerrar_demanda(db, demanda.id)

    ativas = await demandas_service.listar_demandas_ativas(db)
    assert ativas == []


async def test_timeout_em_demanda_gera_atividade_log_e_reverte_status(db):
    joao = await criar_usuario(db, "joao", "João")
    await fila_service.entrar_na_fila(db, joao)
    await demandas_service.iniciar_atividade(db, joao, "Atendendo chamado longo")

    status = await db.get(StatusColaborador, joao.id)
    status.status_desde = now_utc() - timedelta(minutes=51)
    await db.commit()

    revertidos = await verificar_timeouts(db)
    assert revertidos == 1

    status = await db.get(StatusColaborador, joao.id)
    assert status.status_tipo == StatusTipo.na_fila

    from sqlalchemy import select

    logs = (await db.execute(select(AtividadeLog))).scalars().all()
    assert len(logs) == 1
    assert logs[0].tipo == "demanda_timeout"
    assert "Timeout automático" in logs[0].motivo


async def test_timeout_almoco_gera_evento_log(db):
    joao = await criar_usuario(db, "joao", "João")
    await fila_service.entrar_na_fila(db, joao)
    await fila_service.atualizar_status(db, joao, StatusTipo.almoco)

    status = await db.get(StatusColaborador, joao.id)
    status.status_desde = now_utc() - timedelta(minutes=61)
    await db.commit()

    revertidos = await verificar_timeouts(db)
    assert revertidos == 1

    status = await db.get(StatusColaborador, joao.id)
    assert status.status_tipo == StatusTipo.na_fila

    from sqlalchemy import select

    eventos = (await db.execute(select(EventoLog))).scalars().all()
    assert len(eventos) == 1
    assert eventos[0].tipo == "timeout_status"


async def test_timeout_nao_dispara_antes_do_prazo(db):
    joao = await criar_usuario(db, "joao", "João")
    await fila_service.entrar_na_fila(db, joao)
    await fila_service.atualizar_status(db, joao, StatusTipo.almoco)

    revertidos = await verificar_timeouts(db)
    assert revertidos == 0

    status = await db.get(StatusColaborador, joao.id)
    assert status.status_tipo == StatusTipo.almoco
