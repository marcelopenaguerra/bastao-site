from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AtividadeLog, ContadorBastao, Usuario


@dataclass
class RankingBastao:
    usuario: Usuario
    rodadas: int
    tempo_total_segundos: int


@dataclass
class ResumoAtividades:
    usuario: Usuario
    quantidade: int
    duracao_total_minutos: float


async def ranking_bastao(db: AsyncSession) -> list[RankingBastao]:
    result = await db.execute(
        select(Usuario, ContadorBastao)
        .join(ContadorBastao, ContadorBastao.usuario_id == Usuario.id)
        .order_by(ContadorBastao.rodadas.desc())
    )
    return [
        RankingBastao(usuario=usuario, rodadas=contador.rodadas, tempo_total_segundos=contador.tempo_total_segundos)
        for usuario, contador in result.all()
    ]


async def resumo_atividades(
    db: AsyncSession, inicio: datetime | None = None, fim: datetime | None = None
) -> list[ResumoAtividades]:
    query = (
        select(
            Usuario,
            func.count(AtividadeLog.id).label("quantidade"),
            func.coalesce(func.sum(AtividadeLog.duracao_minutos), 0.0).label("duracao_total"),
        )
        .join(AtividadeLog, AtividadeLog.usuario_id == Usuario.id)
        .group_by(Usuario.id)
        .order_by(func.count(AtividadeLog.id).desc())
    )
    if inicio is not None:
        query = query.where(AtividadeLog.criado_em >= inicio)
    if fim is not None:
        query = query.where(AtividadeLog.criado_em <= fim)

    result = await db.execute(query)
    return [
        ResumoAtividades(usuario=usuario, quantidade=quantidade, duracao_total_minutos=float(duracao_total))
        for usuario, quantidade, duracao_total in result.all()
    ]


def formatar_tempo(segundos: int) -> str:
    horas, resto = divmod(int(segundos), 3600)
    minutos, _ = divmod(resto, 60)
    return f"{horas}h{minutos:02d}m"
