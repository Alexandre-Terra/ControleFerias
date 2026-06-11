"""Setores padrão — vocabulário canônico real da coluna B das abas de empresa
(ver SETOR_CANONICO no importer). A aba DASHBOARD da planilha é um template
estático com setores fictícios (Financeiro, RH, Marketing) — não semear daqui."""
from app.models import Setor, db

SETORES_PADRAO = [
    "Oficina",
    "Logística",
    "Comercial",
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
