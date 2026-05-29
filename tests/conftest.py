import os
import sys

import pytest
from werkzeug.security import generate_password_hash

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402
from app.models import Gestor, db  # noqa: E402


@pytest.fixture
def app(tmp_path):
    class TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'test.db'}"
        WTF_CSRF_ENABLED = False
        TESTING = True

    application = create_app(TestConfig)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def gestor_admin(app):
    g = Gestor(
        nome="Admin Teste",
        email="admin@teste.com",
        senha_hash=generate_password_hash("senha123"),
        is_admin=True,
        ativo=True,
    )
    db.session.add(g)
    db.session.commit()
    return g


@pytest.fixture
def gestor_comum(app):
    g = Gestor(
        nome="Gestor Teste",
        email="gestor@teste.com",
        senha_hash=generate_password_hash("senha123"),
        is_admin=False,
        ativo=True,
    )
    db.session.add(g)
    db.session.commit()
    return g


@pytest.fixture
def client_admin(app, gestor_admin):
    c = app.test_client()
    c.post("/login", data={"email": gestor_admin.email, "senha": "senha123"})
    return c


@pytest.fixture
def client_gestor(app, gestor_comum):
    c = app.test_client()
    c.post("/login", data={"email": gestor_comum.email, "senha": "senha123"})
    return c
