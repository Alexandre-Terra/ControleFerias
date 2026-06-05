"""Painel de risco — agregações e dataviz (status sempre derivado de hoje)."""
from datetime import date

from flask import Blueprint, current_app, render_template
from sqlalchemy.orm import joinedload

from ..auth import current_user, filtrar_por_escopo, login_required
from ..models import Funcionario
from .. import dashviz

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@login_required
def index():
    hoje = date.today()
    dav = current_app.config["ALERTA_A_VENCER_DIAS"]

    funcionarios = filtrar_por_escopo(
        Funcionario.query.options(
            joinedload(Funcionario.periodos),
            joinedload(Funcionario.programacoes),
            joinedload(Funcionario.empresa),
            joinedload(Funcionario.setor),
        ).filter(Funcionario.ativo.is_(True)),
        current_user(),
    ).all()

    dados = dashviz.dashboard_dados(funcionarios, hoje, dav)
    return render_template("dashboard.html", d=dados)
