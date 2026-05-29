"""Testes de login, login_required, admin_required e revalidação de sessão."""
from app.models import Gestor, db


def test_login_ok(app, gestor_admin):
    c = app.test_client()
    r = c.post(
        "/login",
        data={"email": gestor_admin.email, "senha": "senha123"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/")


def test_login_senha_errada(app, gestor_admin):
    c = app.test_client()
    r = c.post(
        "/login",
        data={"email": gestor_admin.email, "senha": "errada"},
        follow_redirects=True,
    )
    assert "incorretos" in r.get_data(as_text=True)


def test_login_gestor_inativo_bloqueado(app, gestor_admin):
    gestor_admin.ativo = False
    db.session.commit()
    c = app.test_client()
    r = c.post(
        "/login",
        data={"email": gestor_admin.email, "senha": "senha123"},
        follow_redirects=True,
    )
    assert "incorretos" in r.get_data(as_text=True)


def test_login_required_redireciona(app):
    c = app.test_client()
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_admin_required_bloqueia_gestor_comum(client_gestor):
    r = client_gestor.get("/gestores/", follow_redirects=False)
    assert r.status_code == 403


def test_admin_required_permite_admin(client_admin):
    r = client_admin.get("/gestores/")
    assert r.status_code == 200


def test_desativacao_desconecta_na_proxima_request(app, gestor_admin):
    """Gestor logado é deslogado se for desativado entre uma request e outra."""
    c = app.test_client()
    c.post("/login", data={"email": gestor_admin.email, "senha": "senha123"})
    # confirma que entrou
    assert c.get("/").status_code == 200

    # desativa fora-da-banda
    gestor_admin.ativo = False
    db.session.commit()

    # próxima request: redirect para login
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_logout(client_admin):
    r = client_admin.post("/logout", follow_redirects=False)
    assert r.status_code == 302
    # após logout, próxima request precisa de login
    r2 = client_admin.get("/", follow_redirects=False)
    assert r2.status_code == 302
    assert "/login" in r2.headers["Location"]
