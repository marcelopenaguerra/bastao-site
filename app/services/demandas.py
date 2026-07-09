import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import as_aware_utc, now_utc
from app.models import AtividadeLog, Demanda, StatusColaborador, StatusTipo, Usuario
from app.services import fila as fila_service


async def criar_demanda(
    db: AsyncSession,
    usuario: Usuario,
    texto: str,
    prioridade: str,
    setor: str | None = None,
    direcionada_para_id: uuid.UUID | None = None,
) -> Demanda:
    demanda = Demanda(
        texto=texto,
        prioridade=prioridade,
        setor=setor,
        criado_por=usuario.id,
        direcionada_para=direcionada_para_id,
    )
    db.add(demanda)
    await db.commit()
    await db.refresh(demanda)
    return demanda


async def encerrar_demanda(db: AsyncSession, demanda_id: int) -> None:
    demanda = await db.get(Demanda, demanda_id)
    if demanda is not None:
        demanda.ativa = False
        await db.commit()


async def listar_demandas_ativas(db: AsyncSession) -> list[Demanda]:
    result = await db.execute(select(Demanda).where(Demanda.ativa.is_(True)).order_by(Demanda.criado_em))
    return list(result.scalars().all())


async def iniciar_atividade(
    db: AsyncSession, usuario: Usuario, atividade_texto: str, demanda_id: int | None = None
) -> None:
    await fila_service.atualizar_status(
        db, usuario, StatusTipo.em_demanda, detalhe=atividade_texto, demanda_atual_id=demanda_id
    )


async def finalizar_atividade(db: AsyncSession, usuario: Usuario, motivo: str = "manual") -> None:
    status = await db.get(StatusColaborador, usuario.id)
    if status is None or status.status_tipo != StatusTipo.em_demanda:
        return

    inicio = as_aware_utc(status.status_desde)
    fim = now_utc()
    duracao_minutos = (fim - inicio).total_seconds() / 60.0

    db.add(
        AtividadeLog(
            usuario_id=usuario.id,
            demanda_id=status.demanda_atual_id,
            atividade_texto=status.status_detalhe or "(sem descrição)",
            tipo="demanda",
            inicio=inicio,
            fim=fim,
            duracao_minutos=duracao_minutos,
            motivo=motivo,
        )
    )

    await fila_service.atualizar_status(db, usuario, StatusTipo.na_fila, commit=False)
    await db.commit()
