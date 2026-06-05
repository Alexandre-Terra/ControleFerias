"""Programação de férias com validações da CLT (aviso de 30 dias, saldo)."""
from datetime import date, timedelta

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    url_for,
)

from ..auth import current_user, login_required
from ..forms import ProgramacaoForm
from ..models import Funcionario, PeriodoAquisitivo, ProgramacaoFerias, db
from .. import status as st

bp = Blueprint("programacao", __name__, url_prefix="/funcionarios")

AVISO_PREVIO_DIAS = 30


def _periodos_elegiveis(funcionario, hoje):
    """Períodos fechados (fim <= hoje) com saldo > 0."""
    return [
        p
        for p in funcionario.periodos
        if p.fim and p.fim <= hoje and (p.dias_restantes or 0) > 0
    ]


@bp.route("/<int:func_id>/programar", methods=["GET", "POST"])
@login_required
def programar(func_id):
    hoje = date.today()
    dav = current_app.config["ALERTA_A_VENCER_DIAS"]
    f = db.get_or_404(Funcionario, func_id)

    elegiveis = _periodos_elegiveis(f, hoje)
    form = ProgramacaoForm()
    form.periodo_id.choices = [
        (
            p.id,
            f"{p.inicio:%d/%m/%Y} a {p.fim:%d/%m/%Y} "
            f"(saldo {p.dias_restantes:g} dias, limite {p.limite_gozo:%d/%m/%Y})"
            if p.limite_gozo
            else f"{p.inicio:%d/%m/%Y} a {p.fim:%d/%m/%Y} (saldo {p.dias_restantes:g} dias)",
        )
        for p in elegiveis
    ]

    if not elegiveis:
        flash("Este funcionário não tem período com direito adquirido e saldo.", "erro")
        return redirect(url_for("funcionarios.detalhe", func_id=func_id))

    if form.validate_on_submit():
        periodo = db.session.get(PeriodoAquisitivo, form.periodo_id.data)
        erros = []

        if periodo is None or periodo.funcionario_id != f.id or periodo not in elegiveis:
            erros.append("Período inválido.")
        if form.data_inicio.data < hoje + timedelta(days=AVISO_PREVIO_DIAS):
            erros.append(
                f"As férias devem ser comunicadas com {AVISO_PREVIO_DIAS} dias de "
                f"antecedência (a partir de {(hoje + timedelta(days=AVISO_PREVIO_DIAS)):%d/%m/%Y})."
            )
        if periodo and form.dias_gozo.data > (periodo.dias_restantes or 0):
            erros.append(
                f"Dias de gozo ({form.dias_gozo.data}) excedem o saldo do período "
                f"({periodo.dias_restantes:g})."
            )

        if erros:
            for e in erros:
                flash(e, "erro")
        else:
            dias = form.dias_gozo.data
            db.session.add(
                ProgramacaoFerias(
                    funcionario_id=f.id,
                    periodo_aquisitivo_id=periodo.id,
                    data_inicio=form.data_inicio.data,
                    dias_gozo=dias,
                    data_fim=form.data_inicio.data + timedelta(days=dias - 1),
                    origem="manual",
                    criado_por_id=current_user().id,
                )
            )
            # Consome o saldo do período para evitar dupla programação.
            periodo.dias_restantes = (periodo.dias_restantes or 0) - dias
            db.session.commit()
            flash("Férias programadas com sucesso.", "ok")
            return redirect(url_for("funcionarios.detalhe", func_id=func_id))

    data_minima = hoje + timedelta(days=AVISO_PREVIO_DIAS)
    if not form.is_submitted():
        form.data_inicio.data = data_minima
        form.dias_gozo.data = 30

    return render_template(
        "programar.html",
        f=f,
        form=form,
        elegiveis=elegiveis,
        data_minima=data_minima,
        fim_previsto=data_minima + timedelta(days=29),
    )
