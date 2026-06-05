"""Testes do comando `flask bootstrap-admin` (bootstrap/ressync de admin por env)."""
from werkzeug.security import check_password_hash, generate_password_hash

from app.models import Gestor, db


def _run(app, email=None, senha=None, nome=None):
    """Roda bootstrap-admin com a config sobrescrita para o teste."""
    app.config["ADMIN_EMAIL"] = email
    app.config["ADMIN_SENHA"] = senha
    app.config["ADMIN_NOME"] = nome if nome is not None else "Administrador"
    return app.test_cli_runner().invoke(args=["bootstrap-admin"])


def test_cria_admin_quando_nao_existe(app):
    r = _run(app, email="Admin@Exemplo.com", senha="segredo123", nome="Chefe")
    assert r.exit_code == 0

    g = Gestor.query.filter_by(email="admin@exemplo.com").first()
    assert g is not None
    assert g.is_admin is True
    assert g.ativo is True
    assert g.nome == "Chefe"
    assert check_password_hash(g.senha_hash, "segredo123")


def test_recupera_admin_desativado_e_rebaixado(app):
    """Caminho principal: destravar uma conta inativa/sem admin via env."""
    g = Gestor(
        nome="Admin Original",
        email="admin@exemplo.com",
        senha_hash=generate_password_hash("senha-antiga"),
        is_admin=False,
        ativo=False,
    )
    db.session.add(g)
    db.session.commit()

    r = _run(app, email="admin@exemplo.com", senha="nova-senha-123")
    assert r.exit_code == 0

    db.session.refresh(g)
    assert g.ativo is True
    assert g.is_admin is True
    assert check_password_hash(g.senha_hash, "nova-senha-123")
    # senha antiga não vale mais
    assert not check_password_hash(g.senha_hash, "senha-antiga")
    # nome existente é preservado (não sobrescrito pelo default)
    assert g.nome == "Admin Original"


def test_noop_quando_env_ausente(app):
    r = _run(app, email=None, senha=None)
    assert r.exit_code == 0
    assert Gestor.query.count() == 0


def test_noop_quando_so_email(app):
    r = _run(app, email="admin@exemplo.com", senha=None)
    assert r.exit_code == 0
    assert Gestor.query.count() == 0


def test_falha_com_senha_curta(app):
    """Env setada mas inválida deve falhar (exit != 0), não criar nada."""
    r = _run(app, email="admin@exemplo.com", senha="123")
    assert r.exit_code != 0
    assert Gestor.query.count() == 0
