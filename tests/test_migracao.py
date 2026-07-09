from sqlalchemy import select

from app.models import (
    AtividadeLog,
    BastaoAtual,
    ContadorBastao,
    Demanda,
    EventoLog,
    FilaPosicao,
    JogoSimonScore,
    StatusColaborador,
    StatusTipo,
    Usuario,
)
from scripts.migrar_dados_legado import interpretar_status, migrar


def test_interpretar_status_variacoes():
    assert interpretar_status("") == (StatusTipo.na_fila, None, False)
    assert interpretar_status("Almoço") == (StatusTipo.almoco, None, False)
    assert interpretar_status("Ausente") == (StatusTipo.ausente, None, False)
    assert interpretar_status("Saída rápida") == (StatusTipo.saida_rapida, None, False)
    assert interpretar_status("Bastão") == (StatusTipo.na_fila, None, True)
    assert interpretar_status("Bastão | Atendendo chamado") == (
        StatusTipo.indisponivel,
        "Atendendo chamado",
        True,
    )
    assert interpretar_status("Bastão | Atividade: Trocar toner") == (
        StatusTipo.em_demanda,
        "Trocar toner",
        True,
    )
    assert interpretar_status("Atividade: Trocar toner") == (
        StatusTipo.em_demanda,
        "Trocar toner",
        False,
    )
    tipo, detalhe, tem_bastao = interpretar_status("Texto nunca visto antes")
    assert tipo == StatusTipo.indisponivel
    assert detalhe == "Texto nunca visto antes"
    assert tem_bastao is False


async def test_migrar_dataset_sintetico_no_formato_legado(db):
    old_usuarios = [
        {"username": "joao", "nome": "João", "is_admin": 0, "ativo": 1},
        {"username": "maria", "nome": "Maria", "is_admin": 1, "ativo": 1},
        {"username": "inativo", "nome": "Pessoa Inativa", "is_admin": 0, "ativo": 0},
    ]

    shared_state = {
        "bastao_queue": ["João", "Maria"],
        "status_texto": {
            "João": "Bastão",
            "Maria": "Almoço",
        },
        "bastao_start_time": "2026-07-01T10:00:00+00:00",
        "bastao_counts": {"João": 3, "Maria": 5},
        "almoco_times": {"Maria": "2026-07-01T11:30:00+00:00"},
        "demanda_start_times": {},
        "simon_ranking": [{"nome": "Maria", "score": 12}, {"nome": "João", "score": 8}],
        "daily_logs": [
            {
                "tipo": "demanda",
                "colaborador": "João",
                "atividade": "Resetar senha",
                "inicio": "2026-07-01T09:00:00+00:00",
                "fim": "2026-07-01T09:20:00+00:00",
                "duracao_minutos": 20.0,
            },
            {
                "tipo": "demanda_timeout",
                "colaborador": "Maria",
                "atividade": "Atendendo chamado longo",
                "inicio": "2026-07-01T08:00:00+00:00",
                "fim": "2026-07-01T08:50:00+00:00",
                "duracao_minutos": 50.0,
                "motivo": "Timeout automático (50 minutos)",
            },
            {
                "timestamp": "2026-07-01T12:00:00+00:00",
                "colaborador": "João",
                "titulo": "Impressora travando",
                "objetivo": "registrar",
                "relato": "Papel enroscado com frequência",
                "resultado": "Trocado o rolete",
            },
        ],
    }

    admin_data = {
        "demandas_publicas": [
            {
                "id": 1,
                "texto": "Reinstalar antivírus no setor X",
                "prioridade": "alta",
                "setor": "TI",
                "criado_em": "2026-07-01T08:30:00+00:00",
                "criado_por": "Maria",
                "ativa": True,
                "direcionada_para": "João",
            }
        ],
        "colaboradores_extras": [],
    }

    relatorio = await migrar(db, old_usuarios, shared_state, admin_data)
    await db.commit()

    assert relatorio.usuarios_criados == 3
    assert relatorio.fila_migrada == 2
    assert relatorio.demandas_migradas == 1
    assert relatorio.atividades_migradas == 2
    assert relatorio.eventos_migrados == 1
    assert relatorio.scores_migrados == 2
    assert relatorio.status_nao_reconhecidos == []

    usuarios = {u.nome: u for u in (await db.execute(select(Usuario))).scalars().all()}
    assert set(usuarios) == {"João", "Maria", "Pessoa Inativa"}
    assert usuarios["Maria"].is_admin is True
    assert usuarios["Pessoa Inativa"].ativo is False
    assert usuarios["João"].must_change_password is True

    fila = (await db.execute(select(FilaPosicao))).scalars().all()
    posicoes = {fp.usuario_id: fp.posicao for fp in fila}
    assert posicoes[usuarios["João"].id] == 1
    assert posicoes[usuarios["Maria"].id] == 2

    bastao = await db.get(BastaoAtual, 1)
    assert bastao.usuario_id == usuarios["João"].id

    status_joao = await db.get(StatusColaborador, usuarios["João"].id)
    assert status_joao.status_tipo == StatusTipo.na_fila
    status_maria = await db.get(StatusColaborador, usuarios["Maria"].id)
    assert status_maria.status_tipo == StatusTipo.almoco

    contador_joao = await db.get(ContadorBastao, usuarios["João"].id)
    assert contador_joao.rodadas == 3
    contador_maria = await db.get(ContadorBastao, usuarios["Maria"].id)
    assert contador_maria.rodadas == 5

    demandas = (await db.execute(select(Demanda))).scalars().all()
    assert len(demandas) == 1
    assert demandas[0].criado_por == usuarios["Maria"].id
    assert demandas[0].direcionada_para == usuarios["João"].id

    atividades = (await db.execute(select(AtividadeLog))).scalars().all()
    tipos = sorted(a.tipo for a in atividades)
    assert tipos == ["demanda", "demanda_timeout"]

    eventos = (await db.execute(select(EventoLog))).scalars().all()
    assert len(eventos) == 1
    assert eventos[0].detalhes["titulo"] == "Impressora travando"

    scores = (await db.execute(select(JogoSimonScore))).scalars().all()
    assert {s.score for s in scores} == {12, 8}


async def test_migrar_status_nao_reconhecido_fica_no_relatorio(db):
    old_usuarios = [{"username": "ana", "nome": "Ana", "is_admin": 0, "ativo": 1}]
    shared_state = {
        "bastao_queue": ["Ana"],
        "status_texto": {"Ana": "Em reunião externa"},
        "bastao_counts": {},
    }

    relatorio = await migrar(db, old_usuarios, shared_state, {})
    await db.commit()

    assert relatorio.status_nao_reconhecidos == ["Ana: 'Em reunião externa'"]
    usuario = (await db.execute(select(Usuario))).scalar_one()
    status = await db.get(StatusColaborador, usuario.id)
    assert status.status_tipo == StatusTipo.indisponivel
    assert status.status_detalhe == "Em reunião externa"


async def test_migrar_nome_na_fila_sem_usuario_correspondente_gera_aviso(db):
    old_usuarios = [{"username": "ana", "nome": "Ana", "is_admin": 0, "ativo": 1}]
    shared_state = {"bastao_queue": ["Ana", "Fantasma"], "status_texto": {}}

    relatorio = await migrar(db, old_usuarios, shared_state, {})
    await db.commit()

    assert relatorio.fila_migrada == 1
    assert any("Fantasma" in aviso for aviso in relatorio.avisos)
