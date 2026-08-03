"""Saldo derivado: renomeia dias_restantes p/ saldo_snapshot e marca a data-retrato.

O nome antigo prometia "saldo atual", mas a coluna guardava o AG congelado da
planilha — causa do saldo menor que o real em produção (período que fechava
depois do import ficava com o proporcional do retrato em vez de 30). O saldo
atual passa a ser derivado em runtime (``app/status.py``): base do período menos
programações registradas.

Duas mudanças de dados, ambas determinísticas (sem ``date.today()`` — a migration
c7d1a9e4f2b8 dependia do relógio do deploy e produziu dados divergentes):

- ``snapshot_em`` = 2026-05-27 em todas as linhas existentes: a data-retrato da
  planilha do import original. Nada além do importer criava períodos antes desta
  migration, então todas as linhas vêm dela.
- Devolve ao ``saldo_snapshot`` os débitos feitos pelo app: ``programar`` debitava
  a coluna na criação e ``cancelar`` apagava a linha devolvendo o débito, logo
  TODA programação existente com FK é um débito ainda aplicado (encerradas
  inclusive). Depois disso a coluna volta a significar "AG na data-retrato".

Revision ID: e1a7c9d3b5f2
Revises: b2f4c1d7e9a0
"""
from datetime import date

import sqlalchemy as sa
from alembic import op

revision = "e1a7c9d3b5f2"
down_revision = "b2f4c1d7e9a0"
branch_labels = None
depends_on = None

# Data-retrato da planilha Controle_Ferias_Master_Geral.xlsx do import original.
SNAPSHOT_IMPORT = date(2026, 5, 27)

_DEVOLVE_DEBITOS = """
    UPDATE periodo_aquisitivo
       SET saldo_snapshot = COALESCE(saldo_snapshot, 0) {sinal} (
           SELECT COALESCE(SUM(dias_gozo), 0)
             FROM programacao_ferias
            WHERE programacao_ferias.periodo_aquisitivo_id = periodo_aquisitivo.id)
     WHERE id IN (SELECT periodo_aquisitivo_id FROM programacao_ferias
                   WHERE periodo_aquisitivo_id IS NOT NULL)
"""


def upgrade():
    # batch: env.py não usa render_as_batch; no SQLite o rename recria a tabela
    # (constraints nomeadas sobrevivem), no Postgres vira ALTER TABLE direto.
    with op.batch_alter_table("periodo_aquisitivo") as batch:
        batch.add_column(sa.Column("snapshot_em", sa.Date(), nullable=True))
        batch.alter_column(
            "dias_restantes",
            new_column_name="saldo_snapshot",
            existing_type=sa.Float(),
            existing_nullable=True,
        )
    bind = op.get_bind()
    bind.execute(
        sa.text("UPDATE periodo_aquisitivo SET snapshot_em = :d"),
        {"d": SNAPSHOT_IMPORT},
    )
    bind.execute(sa.text(_DEVOLVE_DEBITOS.format(sinal="+")))


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text(_DEVOLVE_DEBITOS.format(sinal="-")))
    with op.batch_alter_table("periodo_aquisitivo") as batch:
        batch.alter_column(
            "saldo_snapshot",
            new_column_name="dias_restantes",
            existing_type=sa.Float(),
            existing_nullable=True,
        )
        batch.drop_column("snapshot_em")
