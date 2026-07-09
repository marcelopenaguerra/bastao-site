from app.models import StatusTipo
from app.services import fila as fila_service
from tests.conftest import criar_usuario


async def test_entrar_na_fila_assume_bastao_quando_vazio(db):
    joao = await criar_usuario(db, "joao", "João")

    await fila_service.entrar_na_fila(db, joao)

    fila = await fila_service.listar_fila(db)
    assert len(fila) == 1
    assert fila[0].tem_bastao is True
    assert fila[0].status_tipo == StatusTipo.na_fila


async def test_segundo_a_entrar_nao_assume_bastao(db):
    joao = await criar_usuario(db, "joao", "João")
    maria = await criar_usuario(db, "maria", "Maria")

    await fila_service.entrar_na_fila(db, joao)
    await fila_service.entrar_na_fila(db, maria)

    fila = await fila_service.listar_fila(db)
    por_nome = {c.usuario.nome: c for c in fila}
    assert por_nome["João"].tem_bastao is True
    assert por_nome["Maria"].tem_bastao is False


async def test_transferir_bastao_credita_rodada_e_move_para_proximo(db):
    joao = await criar_usuario(db, "joao", "João")
    maria = await criar_usuario(db, "maria", "Maria")
    await fila_service.entrar_na_fila(db, joao)
    await fila_service.entrar_na_fila(db, maria)

    await fila_service.transferir_bastao(db)

    fila = await fila_service.listar_fila(db)
    por_nome = {c.usuario.nome: c for c in fila}
    assert por_nome["Maria"].tem_bastao is True
    assert por_nome["João"].tem_bastao is False
    assert por_nome["João"].rodadas == 1
    assert por_nome["Maria"].rodadas == 0


async def test_pular_bastao_nao_credita_rodada(db):
    joao = await criar_usuario(db, "joao", "João")
    maria = await criar_usuario(db, "maria", "Maria")
    await fila_service.entrar_na_fila(db, joao)
    await fila_service.entrar_na_fila(db, maria)

    await fila_service.pular_bastao(db)

    fila = await fila_service.listar_fila(db)
    por_nome = {c.usuario.nome: c for c in fila}
    assert por_nome["Maria"].tem_bastao is True
    assert por_nome["João"].rodadas == 0


async def test_mudar_status_para_almoco_transfere_bastao_automaticamente(db):
    joao = await criar_usuario(db, "joao", "João")
    maria = await criar_usuario(db, "maria", "Maria")
    await fila_service.entrar_na_fila(db, joao)
    await fila_service.entrar_na_fila(db, maria)

    await fila_service.atualizar_status(db, joao, StatusTipo.almoco)

    fila = await fila_service.listar_fila(db)
    por_nome = {c.usuario.nome: c for c in fila}
    assert por_nome["João"].status_tipo == StatusTipo.almoco
    assert por_nome["João"].tem_bastao is False
    assert por_nome["Maria"].tem_bastao is True


async def test_sair_da_fila_remove_e_renumera_posicoes(db):
    joao = await criar_usuario(db, "joao", "João")
    maria = await criar_usuario(db, "maria", "Maria")
    ana = await criar_usuario(db, "ana", "Ana")
    await fila_service.entrar_na_fila(db, joao)
    await fila_service.entrar_na_fila(db, maria)
    await fila_service.entrar_na_fila(db, ana)

    await fila_service.sair_da_fila(db, maria)

    fila = await fila_service.listar_fila(db)
    nomes_e_posicoes = sorted((c.usuario.nome, c.posicao) for c in fila)
    assert nomes_e_posicoes == [("Ana", 2), ("João", 1)]


async def test_sair_da_fila_com_bastao_repassa_para_proximo(db):
    joao = await criar_usuario(db, "joao", "João")
    maria = await criar_usuario(db, "maria", "Maria")
    await fila_service.entrar_na_fila(db, joao)
    await fila_service.entrar_na_fila(db, maria)

    await fila_service.sair_da_fila(db, joao)

    fila = await fila_service.listar_fila(db)
    assert fila[0].usuario.nome == "Maria"
    assert fila[0].tem_bastao is True
