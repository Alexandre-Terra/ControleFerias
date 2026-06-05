"""Configuração da aplicação, lida de variáveis de ambiente."""
import os


def _normalize_db_url(url: str) -> str:
    """Provedores (Railway, Render, Heroku) costumam entregar ``postgres://``
    ou ``postgresql://``; SQLAlchemy 2 + psycopg querem ``postgresql+psycopg://``.
    Mantém SQLite e outras URLs intactas."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-key")
    SQLALCHEMY_DATABASE_URI = _normalize_db_url(
        os.environ.get("DATABASE_URL", "sqlite:///local.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Dias antes do limite de gozo (AH) em que o período entra em "A vencer".
    ALERTA_A_VENCER_DIAS = int(os.environ.get("ALERTA_A_VENCER_DIAS", "60"))

    # Bootstrap do admin via ambiente (usado por `flask bootstrap-admin`, que roda
    # no deploy). Sem fallback: se ADMIN_EMAIL/ADMIN_SENHA não estiverem setados,
    # o comando vira no-op. Ver app/cli.py.
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")
    ADMIN_NOME = os.environ.get("ADMIN_NOME", "Administrador")
    ADMIN_SENHA = os.environ.get("ADMIN_SENHA")
