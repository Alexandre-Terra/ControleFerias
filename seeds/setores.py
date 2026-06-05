"""Setores padrão (da aba DASHBOARD da planilha original)."""
from app.models import Setor, db

SETORES_PADRAO = [
    "Financeiro",
    "RH",
    "Oficina",
    "Logística",
    "Comercial",
    "Marketing",
    # Vindos da coluna B das abas de empresa (ver SETOR_CANONICO no importer).
    "Administrativo",
    "Licitação",
    "Obras",
]


def seed_setores():
    criados = 0
    for nome in SETORES_PADRAO:
        if not db.session.query(Setor).filter_by(nome=nome).first():
            db.session.add(Setor(nome=nome))
            criados += 1
    db.session.commit()
    return criados
