"""Página "Tempo Funcionários" (admin) — marcos por data de admissão.

Mostra, para cada colaborador ativo, o tempo de casa e o próximo marco de tempo
de serviço (45/90/120 dias e aniversários, ver ``app/tempo.py``), além de
destacar os marcos cujo aviso cai hoje — exatamente os que entram no resumo do
WhatsApp. Apenas admin: a visão é da empresa toda, sem recorte por setor.
"""
from datetime import date

from flask import Blueprint, render_template, request
from sqlalchemy.orm import joinedload

from ..auth import admin_required
from ..models import ConfiguracaoZapi, Funcionario, Setor
from .. import tempo as tp

bp = Blueprint("tempo", __name__, url_prefix="/tempo-funcionarios")

# Filtro por tipo do próximo marco: (valor na URL, rótulo no select).
MARCO_OPCOES = [
    ("45", "45 dias"),
    ("90", "90 dias"),
    ("120", "120 dias"),
    ("aniversario", "Aniversário"),
]


@bp.route("/")
@admin_required
def index():
    hoje = date.today()

    busca = (request.args.get("busca") or "").strip()
    setor_id = request.args.get("setor", type=int)
    marco = (request.args.get("marco") or "").strip()  # "45"|"90"|"120"|"aniversario"

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

    # Total de colaboradores com admissão (antes de aplicar os filtros da tabela).
    total_com_admissao = len(linhas)

    # Filtros (em Python, sobre o conjunto já carregado) — só a tabela; o painel
    # "Avisos de hoje" e a contagem "sem admissão" seguem sobre todos.
    if busca:
        b = busca.lower()
        linhas = [l for l in linhas
                  if b in l["f"].nome.lower() or b in (l["f"].codigo or "").lower()]
    if setor_id:
        linhas = [l for l in linhas if l["f"].setor_id == setor_id]
    if marco:
        linhas = [l for l in linhas if l["proximo"] and (
            (marco == "aniversario" and l["proximo"]["tipo"] == "aniversario")
            or l["proximo"]["label"] == f"{marco} dias")]

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
        total_com_admissao=total_com_admissao,
        setores=Setor.query.order_by(Setor.nome).all(),
        marco_opcoes=MARCO_OPCOES,
        filtros={"busca": busca, "setor": setor_id, "marco": marco},
        zapi_ativo=cfg.pronta() and cfg.notificar_tempo_servico,
    )
