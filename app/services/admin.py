import secrets

from sqlalchemy import func, select, text
from sqlalchemy.engine import Row
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password
from app.models import ContadorBastao, Demanda, FilaPosicao, Usuario


async def listar_usuarios(db: AsyncSession) -> list[Usuario]:
    result = await db.execute(select(Usuario).order_by(Usuario.nome))
    return list(result.scalars().all())


async def criar_usuario(db: AsyncSession, username: str, nome: str, is_admin: bool = False) -> tuple[Usuario, str]:
    senha_temporaria = secrets.token_urlsafe(9)
    usuario = Usuario(
        username=username,
        nome=nome,
        senha_hash=hash_password(senha_temporaria),
        is_admin=is_admin,
        must_change_password=True,
    )
    db.add(usuario)
    await db.commit()
    await db.refresh(usuario)
    return usuario, senha_temporaria


async def alternar_ativo(db: AsyncSession, usuario_id, ativo: bool) -> None:
    usuario = await db.get(Usuario, usuario_id)
    if usuario is not None:
        usuario.ativo = ativo
        await db.commit()


async def resetar_senha(db: AsyncSession, usuario_id) -> str | None:
    usuario = await db.get(Usuario, usuario_id)
    if usuario is None:
        return None
    senha_temporaria = secrets.token_urlsafe(9)
    usuario.senha_hash = hash_password(senha_temporaria)
    usuario.must_change_password = True
    await db.commit()
    return senha_temporaria


async def estatisticas_gerais(db: AsyncSession) -> dict:
    total_usuarios = (await db.execute(select(func.count()).select_from(Usuario))).scalar_one()
    usuarios_ativos = (
        await db.execute(select(func.count()).select_from(Usuario).where(Usuario.ativo.is_(True)))
    ).scalar_one()
    na_fila_agora = (await db.execute(select(func.count()).select_from(FilaPosicao))).scalar_one()
    demandas_ativas = (
        await db.execute(select(func.count()).select_from(Demanda).where(Demanda.ativa.is_(True)))
    ).scalar_one()
    total_rodadas = (
        await db.execute(select(func.coalesce(func.sum(ContadorBastao.rodadas), 0)))
    ).scalar_one()

    return {
        "total_usuarios": total_usuarios,
        "usuarios_ativos": usuarios_ativos,
        "na_fila_agora": na_fila_agora,
        "demandas_ativas": demandas_ativas,
        "total_rodadas": total_rodadas,
    }


class ConsultaNaoPermitida(Exception):
    pass


async def executar_select(db: AsyncSession, consulta: str) -> tuple[list[str], list[Row]]:
    """Executa uma consulta somente-leitura. Só aceita um único SELECT, sempre com rollback ao final."""
    normalizada = consulta.strip().rstrip(";").strip()
    if not normalizada.lower().startswith("select"):
        raise ConsultaNaoPermitida("Somente consultas SELECT são permitidas.")
    if ";" in normalizada:
        raise ConsultaNaoPermitida("Não é permitido executar múltiplas instruções.")

    try:
        resultado = await db.execute(text(normalizada))
        colunas = list(resultado.keys())
        linhas = resultado.fetchall()
        return colunas, linhas
    except SQLAlchemyError as exc:
        raise ConsultaNaoPermitida(str(exc)) from exc
    finally:
        await db.rollback()
