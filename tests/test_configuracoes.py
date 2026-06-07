"""Testes da página de Configurações e da troca self-service de senha."""
from app.models import Gestor, db
from werkzeug.security import check_password_hash


def test_hub_exige_login(app):
    c = app.test_client()
    r = c.get("/configuracoes/", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_hub_logado(client_admin):
    r = client_admin.get("/configuracoes/")
    assert r.status_code == 200
    assert "Configurações" in r.get_data(as_text=True)


def test_alterar_senha_ok(client_admin, gestor_admin):
    r = client_admin.post(
        "/configuracoes/senha",
        data={
            "senha_atual": "senha123",
            "senha": "novasenha",
            "confirmar": "novasenha",
        },
        follow_redirects=True,
    )
    assert "alterada" in r.get_data(as_text=True)
    # senha nova loga; senha antiga não
    c = client_admin.application.test_client()
    r_nova = c.post(
        "/login",
        data={"email": gestor_admin.email, "senha": "novasenha"},
        follow_redirects=False,
    )
    assert r_nova.status_code == 302
    r_antiga = c.post(
        "/login",
        data={"email": gestor_admin.email, "senha": "senha123"},
        follow_redirects=True,
    )
    assert "incorretos" in r_antiga.get_data(as_text=True)


def test_alterar_senha_atual_errada(client_admin, gestor_admin):
    r = client_admin.post(
        "/configuracoes/senha",
        data={
            "senha_atual": "errada",
            "senha": "novasenha",
            "confirmar": "novasenha",
        },
        follow_redirects=True,
    )
    assert "incorreta" in r.get_data(as_text=True)
    # senha não mudou
    g = db.session.get(Gestor, gestor_admin.id)
    assert check_password_hash(g.senha_hash, "senha123")


def test_alterar_senha_confirmacao_diferente(client_admin):
    r = client_admin.post(
        "/configuracoes/senha",
        data={
            "senha_atual": "senha123",
            "senha": "novasenha",
            "confirmar": "outracoisa",
        },
        follow_redirects=True,
    )
    assert "não conferem" in r.get_data(as_text=True)
