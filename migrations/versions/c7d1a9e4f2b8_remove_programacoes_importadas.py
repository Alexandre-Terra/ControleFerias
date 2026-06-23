"""Remove programações importadas da planilha.

Programações de férias passam a nascer exclusivamente no app — a planilha
é apenas base de funcionários/períodos/saldos, e o importer não lê mais as
colunas W/X. Esta migration apaga as ``origem=import`` remanescentes:

- Não encerradas (fim >= hoje): apaga e **devolve** ``dias_gozo`` ao saldo do
  período vinculado (espelha o cancelamento pela UI) — a programação nunca
  valeu, então os dias continuam disponíveis.
- Encerradas (fim < hoje): apaga sem devolver saldo — os dias foram gozados
  de fato e o AG da planilha já os descontou.

Irreversível (downgrade é no-op): os dados removidos vinham da planilha e
podem ser reconstituídos por ela se necessário.
"""
from datetime import date

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c7d1a9e4f2b8"
down_revision = "63859db4e304"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    hoje = date.today()

    progs = bind.execute(
        sa.text(
            "SELECT id, periodo_aquisitivo_id, dias_gozo, data_fim, data_inicio "
            "FROM programacao_ferias WHERE origem = 'import'"
        )
    ).fetchall()

    for pid, periodo_id, dias_gozo, data_fim, data_inicio in progs:
        fim = data_fim or data_inicio
        if isinstance(fim, str):  # SQLite devolve ISO string
            fim = date.fromisoformat(fim)
        if periodo_id is not None and fim is not None and fim >= hoje:
            bind.execute(
                sa.text(
                    "UPDATE periodo_aquisitivo "
                    "SET dias_restantes = COALESCE(dias_restantes, 0) + :dias "
                    "WHERE id = :pid"
                ),
                {"dias": dias_gozo or 0, "pid": periodo_id},
            )
        bind.execute(
            sa.text("DELETE FROM programacao_ferias WHERE id = :id"), {"id": pid}
        )


def downgrade():
    pass
