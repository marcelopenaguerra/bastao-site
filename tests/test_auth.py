from app.auth.security import hash_password, verify_password
from tests.conftest import criar_usuario


def test_hash_password_and_verify():
    hash_ = hash_password("minha-senha-123")
    assert verify_password("minha-senha-123", hash_)
    assert not verify_password("senha-errada", hash_)


async def test_login_sucesso_permite_acesso_ao_dashboard(db, client):
    await criar_usuario(db, "joao", "João Teste")

    resposta = await client.post(
        "/login", data={"identificador": "joao", "senha": "senha-teste-123"}
    )
    assert resposta.status_code == 303

    dashboard = await client.get("/")
    assert dashboard.status_code == 200
    assert "João Teste" in dashboard.text


async def test_login_senha_errada_retorna_401(db, client):
    await criar_usuario(db, "joao", "João Teste")

    resposta = await client.post("/login", data={"identificador": "joao", "senha": "errada"})
    assert resposta.status_code == 401


async def test_dashboard_sem_sessao_redireciona_para_login(client):
    resposta = await client.get("/")
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/login"


async def test_rate_limit_apos_cinco_tentativas_falhas(db, client):
    await criar_usuario(db, "joao", "João Teste")

    for _ in range(5):
        resposta = await client.post("/login", data={"identificador": "joao", "senha": "errada"})
        assert resposta.status_code == 401

    bloqueada = await client.post("/login", data={"identificador": "joao", "senha": "errada"})
    assert bloqueada.status_code == 429

    ainda_bloqueada = await client.post(
        "/login", data={"identificador": "joao", "senha": "senha-teste-123"}
    )
    assert ainda_bloqueada.status_code == 429


async def test_logout_revoga_sessao(db, client):
    await criar_usuario(db, "joao", "João Teste")
    await client.post("/login", data={"identificador": "joao", "senha": "senha-teste-123"})

    await client.post("/logout")

    dashboard = await client.get("/")
    assert dashboard.status_code == 303


async def test_must_change_password_redireciona_para_troca_de_senha(db, client):
    from app.auth.security import hash_password as hp
    from app.models import Usuario

    usuario = Usuario(
        username="novo",
        nome="Novo Usuário",
        senha_hash=hp("senha-teste-123"),
        must_change_password=True,
    )
    db.add(usuario)
    await db.commit()

    resposta = await client.post(
        "/login", data={"identificador": "novo", "senha": "senha-teste-123"}
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/trocar-senha"
