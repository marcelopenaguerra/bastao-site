from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import as_aware_utc, now_utc
from app.models import (
    BastaoAtual,
    BastaoTransferencia,
    ContadorBastao,
    FilaPosicao,
    StatusColaborador,
    StatusTipo,
    Usuario,
)


@dataclass
class ColaboradorFila:
    usuario: Usuario
    posicao: int
    status_tipo: StatusTipo
    status_detalhe: str | None
    rodadas: int
    tem_bastao: bool


async def get_bastao_atual(db: AsyncSession) -> BastaoAtual:
    bastao = await db.get(BastaoAtual, 1)
    if bastao is None:
        bastao = BastaoAtual(id=1, usuario_id=None, desde=None)
        db.add(bastao)
        await db.flush()
    return bastao


async def listar_fila(db: AsyncSession) -> list[ColaboradorFila]:
    result = await db.execute(
        select(FilaPosicao, Usuario, StatusColaborador, ContadorBastao)
        .join(Usuario, Usuario.id == FilaPosicao.usuario_id)
        .outerjoin(StatusColaborador, StatusColaborador.usuario_id == FilaPosicao.usuario_id)
        .outerjoin(ContadorBastao, ContadorBastao.usuario_id == FilaPosicao.usuario_id)
        .order_by(FilaPosicao.posicao)
    )
    bastao = await get_bastao_atual(db)
    colaboradores = []
    for fila_pos, usuario, status, contador in result.all():
        colaboradores.append(
            ColaboradorFila(
                usuario=usuario,
                posicao=fila_pos.posicao,
                status_tipo=status.status_tipo if status else StatusTipo.indisponivel,
                status_detalhe=status.status_detalhe if status else None,
                rodadas=contador.rodadas if contador else 0,
                tem_bastao=(bastao.usuario_id == usuario.id),
            )
        )
    return colaboradores


async def entrar_na_fila(db: AsyncSession, usuario: Usuario) -> None:
    if await db.get(FilaPosicao, usuario.id) is not None:
        return

    max_pos = (await db.execute(select(func.max(FilaPosicao.posicao)))).scalar_one_or_none() or 0
    db.add(FilaPosicao(usuario_id=usuario.id, posicao=max_pos + 1))

    status = await db.get(StatusColaborador, usuario.id)
    if status is None:
        db.add(StatusColaborador(usuario_id=usuario.id, status_tipo=StatusTipo.na_fila))
    else:
        status.status_tipo = StatusTipo.na_fila
        status.status_detalhe = None
        status.status_desde = now_utc()

    if await db.get(ContadorBastao, usuario.id) is None:
        db.add(ContadorBastao(usuario_id=usuario.id))

    await db.flush()

    bastao = await get_bastao_atual(db)
    if bastao.usuario_id is None:
        bastao.usuario_id = usuario.id
        bastao.desde = now_utc()

    await db.commit()


async def sair_da_fila(db: AsyncSession, usuario: Usuario) -> None:
    posicao = await db.get(FilaPosicao, usuario.id)
    if posicao is None:
        return

    segurava_bastao = (await get_bastao_atual(db)).usuario_id == usuario.id

    await db.delete(posicao)
    await db.flush()

    restantes = (await db.execute(select(FilaPosicao).order_by(FilaPosicao.posicao))).scalars().all()
    for i, fp in enumerate(restantes, start=1):
        fp.posicao = i

    if segurava_bastao:
        await _avancar_bastao(db, motivo="saida_da_fila", creditar=False)

    await db.commit()


async def _proximo_disponivel(db: AsyncSession, a_partir_de_posicao: int) -> Usuario | None:
    linhas = (
        await db.execute(
            select(FilaPosicao, Usuario, StatusColaborador)
            .join(Usuario, Usuario.id == FilaPosicao.usuario_id)
            .outerjoin(StatusColaborador, StatusColaborador.usuario_id == FilaPosicao.usuario_id)
            .order_by(FilaPosicao.posicao)
        )
    ).all()
    if not linhas:
        return None

    n = len(linhas)
    indice_atual = next(
        (i for i, (fp, _, _) in enumerate(linhas) if fp.posicao == a_partir_de_posicao), -1
    )

    for offset in range(1, n + 1):
        _, usuario, status = linhas[(indice_atual + offset) % n]
        if status is not None and status.status_tipo == StatusTipo.na_fila:
            return usuario

    return None


async def _avancar_bastao(db: AsyncSession, motivo: str, creditar: bool) -> None:
    bastao = await get_bastao_atual(db)
    detentor_anterior_id = bastao.usuario_id

    if creditar and detentor_anterior_id is not None and bastao.desde is not None:
        contador = await db.get(ContadorBastao, detentor_anterior_id)
        if contador is None:
            contador = ContadorBastao(usuario_id=detentor_anterior_id)
            db.add(contador)
        segundos = int((now_utc() - as_aware_utc(bastao.desde)).total_seconds())
        contador.rodadas += 1
        contador.tempo_total_segundos += max(segundos, 0)

    posicao_anterior = 0
    if detentor_anterior_id is not None:
        fp = await db.get(FilaPosicao, detentor_anterior_id)
        if fp is not None:
            posicao_anterior = fp.posicao

    proximo = await _proximo_disponivel(db, posicao_anterior)

    novo_usuario_id = proximo.id if proximo else None
    bastao.usuario_id = novo_usuario_id
    bastao.desde = now_utc() if novo_usuario_id is not None else None

    db.add(
        BastaoTransferencia(
            de_usuario_id=detentor_anterior_id,
            para_usuario_id=novo_usuario_id,
            motivo=motivo,
        )
    )


async def transferir_bastao(db: AsyncSession) -> None:
    await _avancar_bastao(db, motivo="manual", creditar=True)
    await db.commit()


async def pular_bastao(db: AsyncSession) -> None:
    await _avancar_bastao(db, motivo="pular", creditar=False)
    await db.commit()


async def atualizar_status(
    db: AsyncSession,
    usuario: Usuario,
    status_tipo: StatusTipo,
    detalhe: str | None = None,
    demanda_atual_id: int | None = None,
    commit: bool = True,
) -> None:
    status = await db.get(StatusColaborador, usuario.id)
    if status is None:
        status = StatusColaborador(usuario_id=usuario.id)
        db.add(status)

    status.status_tipo = status_tipo
    status.status_detalhe = detalhe
    status.demanda_atual_id = demanda_atual_id
    status.status_desde = now_utc()

    bastao = await get_bastao_atual(db)
    if status_tipo != StatusTipo.na_fila and bastao.usuario_id == usuario.id:
        await _avancar_bastao(db, motivo=f"status:{status_tipo.value}", creditar=True)

    if commit:
        await db.commit()
