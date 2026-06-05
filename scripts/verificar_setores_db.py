"""Diagnóstico read-only: no banco apontado por DATABASE_URL, mostra quantos
funcionários têm setor, os setores cadastrados e uma amostra. Use para confirmar
em QUAL banco o backfill de setores realmente caiu.

Uso (no mesmo terminal onde você setou DATABASE_URL para a URL pública do
Postgres da prod):

    .venv\\Scripts\\python.exe scripts\\verificar_setores_db.py

Não grava nada. Pode apagar este arquivo depois.
"""
import os
import re
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import _normalize_db_url  # noqa: E402

url = os.environ.get("DATABASE_URL")
if not url:
    sys.exit(
        "DATABASE_URL não está setado neste terminal.\n"
        "Defina com a URL PÚBLICA do Postgres e rode de novo, ex.:\n"
        '  $env:DATABASE_URL = "postgresql://postgres:SENHA@HOST.proxy.rlwy.net:PORTA/railway"'
    )

masked = re.sub(r"//([^:]+):[^@]+@", r"//\1:***@", url)
print("DATABASE_URL :", masked)

eng = create_engine(_normalize_db_url(url))
with eng.connect() as c:
    print("database     :", c.execute(text("select current_database()")).scalar())
    total = c.execute(text("select count(*) from funcionario")).scalar()
    com = c.execute(
        text("select count(*) from funcionario where setor_id is not null")
    ).scalar()
    print(f"funcionarios : {total}  |  com setor: {com}  |  sem setor: {total - com}")

    print("\nsetores (nome -> nº de funcionários):")
    for nome, qtd in c.execute(text(
        "select s.nome, count(f.id) from setor s "
        "left join funcionario f on f.setor_id = s.id "
        "group by s.nome order by s.nome"
    )):
        print(f"  {nome:16s} {qtd}")

    print("\namostra (5 funcionários):")
    for cod, nome, setor in c.execute(text(
        "select f.codigo, f.nome, s.nome from funcionario f "
        "left join setor s on s.id = f.setor_id order by f.nome limit 5"
    )):
        print(f"  #{str(cod):6s} {str(nome)[:28]:28s} -> {setor}")
