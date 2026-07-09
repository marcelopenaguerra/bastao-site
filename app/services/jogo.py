from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JogoSimonScore, Usuario


@dataclass
class RankingSimon:
    usuario: Usuario
    melhor_score: int


async def registrar_score(db: AsyncSession, usuario: Usuario, score: int) -> None:
    db.add(JogoSimonScore(usuario_id=usuario.id, score=score))
    await db.commit()


async def ranking_top5(db: AsyncSession) -> list[RankingSimon]:
    result = await db.execute(
        select(Usuario, func.max(JogoSimonScore.score).label("melhor_score"))
        .join(JogoSimonScore, JogoSimonScore.usuario_id == Usuario.id)
        .group_by(Usuario.id)
        .order_by(func.max(JogoSimonScore.score).desc())
        .limit(5)
    )
    return [RankingSimon(usuario=usuario, melhor_score=melhor_score) for usuario, melhor_score in result.all()]
