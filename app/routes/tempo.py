"""Página "Tempo Funcionários" (admin) — marcos por data de admissão.

Mostra, para cada colaborador ativo, o tempo de casa e o próximo marco de tempo
de serviço (45/90/120 dias e aniversários, ver ``app/tempo.py``), além de
destacar os marcos cujo aviso cai hoje — exatamente os que entram no resumo do
WhatsApp. Apenas admin: a visão é da empresa toda, sem recorte por setor.
"""
from datetime import date

from flask import Blueprint, render_template
from sqlalchemy.orm import joinedload

from ..auth import admin_required
from ..models import ConfiguracaoZapi, Funcionario
from .. import tempo as tp

bp = Blueprint("tempo", __name__, url_prefix="/tempo-funcionarios")


@bp.route("/")
@admin_required
def index():
    hoje = date.today()
    funcionarios = (
        Funcionario.query.filter(Funcionario.ativo.is_(True))
        .options(joinedload(Funcionario.empresa), joinedload(Funcionario.setor))
        .order_by(Funcionario.nome)
        .all()
    )

    linhas = []
    alertas_hoje = []
    sem_admissao = 0
    for f in funcionarios:
        if f.data_admissao is None:
            sem_admissao += 1
            continue
        linhas.append(
            {
                "f": f,
                "proximo": tp.proximo_marco(f.data_admissao, hoje),
                "tempo_casa": tp.descricao_tempo_casa(f.data_admissao, hoje),
            }
        )
        for mk in tp.alertas_do_dia(f.data_admissao, hoje):
            alertas_hoje.append({"f": f, "marco": mk})

    # Ordena pela urgência do próximo marco (menos dias primeiro).
    linhas.sort(
        key=lambda l: l["proximo"]["data"] if l["proximo"] else date.max
    )
    alertas_hoje.sort(key=lambda a: (a["marco"]["data"], a["f"].nome))

    cfg = ConfiguracaoZapi.obter()
    return render_template(
        "tempo_funcionarios.html",
        linhas=linhas,
        alertas_hoje=alertas_hoje,
        sem_admissao=sem_admissao,
        total=len(funcionarios),
        zapi_ativo=cfg.pronta() and cfg.notificar_tempo_servico,
    )
