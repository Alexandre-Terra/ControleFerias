"""Z-API: marcos de tempo de serviço no resumo.

Acrescenta à ``configuracao_zapi`` (singleton) a regra e os modelos do bloco de
"tempo de serviço" — marcos por data de admissão (45/90/120 dias e
aniversários), avisados pelo mesmo envio de WhatsApp:

- ``notificar_tempo_servico``: liga/desliga o bloco (default ligado).
- ``modelo_tempo_cabecalho`` / ``modelo_tempo``: textos editáveis do bloco.

Os ``server_default`` fazem o backfill da linha singleton já existente, mantendo
as três colunas ``NOT NULL`` sem precisar de migração de dados separada.

Revision ID: b2f4c1d7e9a0
Revises: 00756c4f6c94
Create Date: 2026-06-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2f4c1d7e9a0'
down_revision = '00756c4f6c94'
branch_labels = None
depends_on = None


_MODELO_TEMPO_CABECALHO = (
    "⏳ *Tempo de empresa* — {data}\n\n"
    "{total} colaborador(es) com marco de tempo de serviço:\n"
)
_MODELO_TEMPO = "• *{nome}* ({empresa}) — {marco} em {data} (faltam {dias} dia(s))"


def upgrade():
    with op.batch_alter_table('configuracao_zapi', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'notificar_tempo_servico',
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch_op.add_column(
            sa.Column(
                'modelo_tempo_cabecalho',
                sa.Text(),
                nullable=False,
                server_default=_MODELO_TEMPO_CABECALHO,
            )
        )
        batch_op.add_column(
            sa.Column(
                'modelo_tempo',
                sa.Text(),
                nullable=False,
                server_default=_MODELO_TEMPO,
            )
        )


def downgrade():
    with op.batch_alter_table('configuracao_zapi', schema=None) as batch_op:
        batch_op.drop_column('modelo_tempo')
        batch_op.drop_column('modelo_tempo_cabecalho')
        batch_op.drop_column('notificar_tempo_servico')
