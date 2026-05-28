"""Dashboard: cards de alerta + agregações por empresa, setor e mês."""
from collections import defaultdict
from datetime import date

from flask import Blueprint, current_app, render_template
from sqlalchemy.orm import joinedload

from ..auth import login_required
from ..models import Funcionario
from .. import status as st

bp = Blueprint("dashboard", __name__)

MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
         "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


@bp.route("/")
@login_required
def index():
    hoje = date.today()
    dav = current_app.config["ALERTA_A_VENCER_DIAS"]

    funcionarios = (
        Funcionario.query.options(
            joinedload(Funcionario.periodos),
            joinedload(Funcionario.programacoes),
            joinedload(Funcionario.empresa),
            joinedload(Funcionario.setor),
        )
        .all()
    )

    cards = {"vencidas": 0, "a_vencer": 0, "programadas": 0,
             "colaboradores": len(funcionarios), "tem_direito": 0}
    por_empresa = defaultdict(lambda: {"total": 0, "vencidas": 0, "a_vencer": 0})
    por_setor = defaultdict(int)
    por_mes = [0] * 12

    for f in funcionarios:
        agregado = st.status_funcionario(f, hoje, dav)
        emp = por_empresa[f.empresa.nome]
        emp["total"] += 1

        if agregado == st.VENCIDA:
            cards["vencidas"] += 1
            emp["vencidas"] += 1
        elif agregado == st.A_VENCER:
            cards["a_vencer"] += 1
            emp["a_vencer"] += 1

        if st.tem_direito(f, hoje, dav):
            cards["tem_direito"] += 1

        tem_prog = any(
            (p.data_fim or p.data_inicio) and (p.data_fim or p.data_inicio) >= hoje
            for p in f.programacoes
        )
        if tem_prog:
            cards["programadas"] += 1

        por_setor[f.setor.nome if f.setor else "Não definido"] += 1

        for p in f.programacoes:
            por_mes[p.data_inicio.month - 1] += 1

    return render_template(
        "dashboard.html",
        cards=cards,
        por_empresa=sorted(por_empresa.items()),
        por_setor=sorted(por_setor.items()),
        por_mes=list(zip(MESES, por_mes)),
    )
