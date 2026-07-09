"""Migra dados do sistema antigo (Streamlit) para o schema relacional novo.

Fontes do sistema antigo (conforme o código-fonte de auth_system.py e
shared_state.py):
  - usuários: tabela `usuarios` no SQLite antigo (bastao_users.db).
  - estado operacional: blob JSON em app_state.state_key='shared_state'
    (chaves: bastao_queue, status_texto, bastao_start_time, bastao_counts,
    simon_ranking, daily_logs, almoco_times, demanda_start_times).
  - dados administrativos: blob JSON em app_state.state_key='admin_data'
    (chaves: colaboradores_extras, demandas_publicas).

Esses blobs podem ser exportados manualmente para arquivos .json (ex: via
`select state_json from app_state where state_key='shared_state'` no Supabase)
e passados via --state-json / --admin-json.

Uso:
    python scripts/migrar_dados_legado.py \
        --old-sqlite ../bastao_users.db \
        --state-json ./shared_state.json \
        --admin-json ./admin_data.json \
        --dry-run

Rode primeiro com --dry-run e revise o relatório (avisos, status não
reconhecidos) antes de rodar de verdade. Faça isso numa janela de baixo
movimento, com o Streamlit antigo pausado durante a extração final.
"""

import argparse
import asyncio
import json
import sqlite3
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth.security import hash_password  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
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


@dataclass
class RelatorioMigracao:
    usuarios_criados: int = 0
    fila_migrada: int = 0
    status_nao_reconhecidos: list[str] = field(default_factory=list)
    demandas_migradas: int = 0
    atividades_migradas: int = 0
    eventos_migrados: int = 0
    scores_migrados: int = 0
    avisos: list[str] = field(default_factory=list)


def _parse_iso(valor) -> datetime | None:
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor
    try:
        return datetime.fromisoformat(valor)
    except (TypeError, ValueError):
        return None


def interpretar_status(raw: str) -> tuple[StatusTipo, str | None, bool]:
    """Traduz o texto livre do sistema antigo (ex: 'Bastão | Atendendo chamado',
    'Almoço', 'Ausente', '', 'Atividade: X') para (status_tipo, detalhe, tem_bastao).

    O sistema antigo codifica "está com o bastão" como a substring 'Bastão'
    dentro do próprio texto de status, em vez de um campo separado — por isso
    o parsing manual em vez de um mapeamento direto de enum.
    """
    texto = (raw or "").strip()
    tem_bastao = "Bastão" in texto

    resto = texto.replace("Bastão | ", "").replace("Bastão", "").strip()

    if not resto:
        return (StatusTipo.na_fila, None, tem_bastao)
    if resto == "Almoço":
        return (StatusTipo.almoco, None, tem_bastao)
    if resto == "Ausente":
        return (StatusTipo.ausente, None, tem_bastao)
    if resto == "Saída rápida":
        return (StatusTipo.saida_rapida, None, tem_bastao)
    if resto.startswith("Atividade:"):
        return (StatusTipo.em_demanda, resto.removeprefix("Atividade:").strip(), tem_bastao)

    # Texto não reconhecido: preserva como detalhe e cai em 'indisponivel'
    # para forçar revisão manual (ver RelatorioMigracao.status_nao_reconhecidos).
    return (StatusTipo.indisponivel, resto, tem_bastao)


async def migrar(
    session,
    old_usuarios: list[dict],
    shared_state: dict,
    admin_data: dict,
) -> RelatorioMigracao:
    """Popula o schema novo a partir dos dados do sistema antigo.

    Não faz commit — quem chama decide (permite --dry-run com rollback).
    """
    relatorio = RelatorioMigracao()

    # 1. Usuários — nunca reaproveita o hash de senha antigo (SHA-256 sem salt,
    # e as senhas padrão já estão expostas em texto plano no repositório antigo).
    usuarios_por_nome: dict[str, Usuario] = {}
    for row in old_usuarios:
        nome = row["nome"]
        senha_temporaria = uuid.uuid4().hex[:12]
        usuario = Usuario(
            username=row["username"],
            nome=nome,
            senha_hash=hash_password(senha_temporaria),
            is_admin=bool(row.get("is_admin")),
            ativo=bool(row.get("ativo", True)),
            must_change_password=True,
        )
        session.add(usuario)
        usuarios_por_nome[nome] = usuario
        relatorio.usuarios_criados += 1
    await session.flush()

    # 2. Fila (bastao_queue: lista de nomes, ordem = ordem da fila)
    bastao_queue = shared_state.get("bastao_queue", [])
    bastao_start_time = _parse_iso(shared_state.get("bastao_start_time"))
    for posicao, nome in enumerate(bastao_queue, start=1):
        usuario = usuarios_por_nome.get(nome)
        if usuario is None:
            relatorio.avisos.append(f"Nome '{nome}' na fila mas sem usuário correspondente — ignorado.")
            continue
        session.add(FilaPosicao(usuario_id=usuario.id, posicao=posicao))
        relatorio.fila_migrada += 1

    # 3. Status de cada colaborador + quem tem o bastão
    almoco_times = shared_state.get("almoco_times", {})
    demanda_start_times = shared_state.get("demanda_start_times", {})
    status_texto = shared_state.get("status_texto", {})

    detentor_bastao_id = None
    for nome, raw in status_texto.items():
        usuario = usuarios_por_nome.get(nome)
        if usuario is None:
            continue
        status_tipo, detalhe, tem_bastao = interpretar_status(raw)
        if status_tipo == StatusTipo.indisponivel and detalhe:
            relatorio.status_nao_reconhecidos.append(f"{nome}: '{raw}'")

        status_desde = (
            _parse_iso(almoco_times.get(nome))
            or _parse_iso(demanda_start_times.get(nome))
            or (bastao_start_time if tem_bastao else None)
            or datetime.now(timezone.utc)
        )
        session.add(
            StatusColaborador(
                usuario_id=usuario.id,
                status_tipo=status_tipo,
                status_detalhe=detalhe,
                status_desde=status_desde,
            )
        )
        if tem_bastao:
            detentor_bastao_id = usuario.id

    session.add(
        BastaoAtual(
            id=1,
            usuario_id=detentor_bastao_id,
            desde=bastao_start_time if detentor_bastao_id else None,
        )
    )

    # 4. Contadores de rodadas
    for nome, rodadas in shared_state.get("bastao_counts", {}).items():
        usuario = usuarios_por_nome.get(nome)
        if usuario is None:
            continue
        session.add(ContadorBastao(usuario_id=usuario.id, rodadas=int(rodadas)))

    # 5. Demandas públicas (admin_data.demandas_publicas)
    for d in admin_data.get("demandas_publicas", []):
        criado_por = usuarios_por_nome.get(d.get("criado_por"))
        direcionada_para = usuarios_por_nome.get(d.get("direcionada_para"))
        session.add(
            Demanda(
                texto=d["texto"],
                prioridade=d.get("prioridade", "normal"),
                setor=d.get("setor"),
                criado_por=criado_por.id if criado_por else None,
                direcionada_para=direcionada_para.id if direcionada_para else None,
                ativa=d.get("ativa", True),
                criado_em=_parse_iso(d.get("criado_em")) or datetime.now(timezone.utc),
            )
        )
        relatorio.demandas_migradas += 1

    # 6. Logs — daily_logs mistura dois formatos: entradas de atividade
    # (tem 'tipo': 'demanda'/'demanda_timeout') e relatos de erro (sem 'tipo',
    # com 'titulo'/'objetivo'/'relato'/'resultado').
    for entry in shared_state.get("daily_logs", []):
        nome = entry.get("colaborador")
        usuario = usuarios_por_nome.get(nome)
        if usuario is None:
            relatorio.avisos.append(f"Log sem usuário correspondente para '{nome}' — ignorado.")
            continue

        if entry.get("tipo") in ("demanda", "demanda_timeout"):
            inicio = _parse_iso(entry.get("inicio")) or datetime.now(timezone.utc)
            fim = _parse_iso(entry.get("fim")) or inicio
            session.add(
                AtividadeLog(
                    usuario_id=usuario.id,
                    atividade_texto=entry.get("atividade") or "(sem descrição)",
                    tipo=entry["tipo"],
                    inicio=inicio,
                    fim=fim,
                    duracao_minutos=float(entry.get("duracao_minutos", 0.0)),
                    motivo=entry.get("motivo"),
                )
            )
            relatorio.atividades_migradas += 1
        else:
            session.add(
                EventoLog(
                    usuario_id=usuario.id,
                    tipo="relato_erro",
                    detalhes={k: v for k, v in entry.items() if k != "colaborador"},
                    criado_em=_parse_iso(entry.get("timestamp")) or datetime.now(timezone.utc),
                )
            )
            relatorio.eventos_migrados += 1

    # 7. Ranking do jogo Simon (já vem como top-5 pré-calculado)
    for item in shared_state.get("simon_ranking", []):
        usuario = usuarios_por_nome.get(item.get("nome"))
        if usuario is None:
            continue
        session.add(JogoSimonScore(usuario_id=usuario.id, score=int(item.get("score", 0))))
        relatorio.scores_migrados += 1

    if admin_data.get("colaboradores_extras"):
        relatorio.avisos.append(
            "admin_data.colaboradores_extras não está vazio — esse campo não tinha consumidor "
            "claro no código antigo; revise manualmente se precisa ser migrado."
        )

    return relatorio


def carregar_usuarios_sqlite(caminho: str) -> list[dict]:
    conn = sqlite3.connect(caminho)
    conn.row_factory = sqlite3.Row
    linhas = conn.execute("SELECT username, nome, is_admin, ativo FROM usuarios").fetchall()
    conn.close()
    return [dict(row) for row in linhas]


def carregar_json(caminho: str) -> dict:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


async def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--old-sqlite", required=True, help="Caminho para o bastao_users.db antigo")
    parser.add_argument("--state-json", help="Caminho para o JSON exportado de app_state.shared_state")
    parser.add_argument("--admin-json", help="Caminho para o JSON exportado de app_state.admin_data")
    parser.add_argument("--dry-run", action="store_true", help="Não grava nada, só mostra o relatório")
    args = parser.parse_args()

    old_usuarios = carregar_usuarios_sqlite(args.old_sqlite)
    shared_state = carregar_json(args.state_json) if args.state_json else {}
    admin_data = carregar_json(args.admin_json) if args.admin_json else {}

    async with SessionLocal() as session:
        relatorio = await migrar(session, old_usuarios, shared_state, admin_data)
        if args.dry_run:
            await session.rollback()
            print("[DRY RUN] Nada foi gravado.")
        else:
            await session.commit()

    print(relatorio)


if __name__ == "__main__":
    asyncio.run(_main())
