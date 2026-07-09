import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import as_aware_utc, now_utc
from app.db import SessionLocal
from app.models import AtividadeLog, EventoLog, StatusColaborador, StatusTipo

logger = logging.getLogger(__name__)

STATUS_TIMEOUTS: dict[StatusTipo, timedelta] = {
    StatusTipo.almoco: timedelta(minutes=60),
    StatusTipo.saida_rapida: timedelta(minutes=15),
    StatusTipo.em_demanda: timedelta(minutes=50),
}

# Chave arbitrária e fixa para o lock consultivo deste job específico no Postgres.
ADVISORY_LOCK_KEY = 583920147


async def _tentar_lock(db: AsyncSession) -> bool:
    if db.bind.dialect.name != "postgresql":
        return True
    resultado = await db.execute(text("SELECT pg_try_advisory_lock(:chave)"), {"chave": ADVISORY_LOCK_KEY})
    return bool(resultado.scalar_one())


async def _liberar_lock(db: AsyncSession) -> None:
    if db.bind.dialect.name != "postgresql":
        return
    await db.execute(text("SELECT pg_advisory_unlock(:chave)"), {"chave": ADVISORY_LOCK_KEY})


async def verificar_timeouts(db: AsyncSession) -> int:
    """Reverte para 'na_fila' quem excedeu o tempo máximo do status atual.

    Protegido por pg_advisory_lock em produção para não processar o mesmo timeout
    duas vezes caso existam múltiplas réplicas do serviço rodando o loop.
    """
    if not await _tentar_lock(db):
        return 0

    try:
        agora = now_utc()
        status_monitorados = (
            await db.execute(
                select(StatusColaborador).where(
                    StatusColaborador.status_tipo.in_(list(STATUS_TIMEOUTS.keys()))
                )
            )
        ).scalars().all()

        revertidos = 0
        for status in status_monitorados:
            limite = STATUS_TIMEOUTS[status.status_tipo]
            if agora - as_aware_utc(status.status_desde) < limite:
                continue

            minutos = int(limite.total_seconds() // 60)
            motivo = f"Timeout automático ({minutos} minutos)"
            inicio = as_aware_utc(status.status_desde)

            if status.status_tipo == StatusTipo.em_demanda:
                db.add(
                    AtividadeLog(
                        usuario_id=status.usuario_id,
                        demanda_id=status.demanda_atual_id,
                        atividade_texto=status.status_detalhe or "(sem descrição)",
                        tipo="demanda_timeout",
                        inicio=inicio,
                        fim=agora,
                        duracao_minutos=(agora - inicio).total_seconds() / 60.0,
                        motivo=motivo,
                    )
                )
            else:
                db.add(
                    EventoLog(
                        usuario_id=status.usuario_id,
                        tipo="timeout_status",
                        detalhes={"status_anterior": status.status_tipo.value, "motivo": motivo},
                    )
                )

            status.status_tipo = StatusTipo.na_fila
            status.status_detalhe = None
            status.demanda_atual_id = None
            status.status_desde = agora
            revertidos += 1

        await db.commit()
        return revertidos
    finally:
        await _liberar_lock(db)


async def loop_timeouts(intervalo_segundos: int = 30) -> None:
    while True:
        try:
            async with SessionLocal() as db:
                revertidos = await verificar_timeouts(db)
                if revertidos:
                    logger.info("timeout automático revertido para %d colaborador(es)", revertidos)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("erro ao verificar timeouts automáticos")
        await asyncio.sleep(intervalo_segundos)
