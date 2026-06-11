"""Programação de férias com validações da CLT (aviso de 30 dias, saldo).

Admin é isento do aviso prévio de 30 dias — pode programar a partir de hoje
(o passado continua bloqueado). Gestores comuns seguem a regra integral.
"""
from datetime import date, timedelta

from flask import (
    Blueprint,
    abort,
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
    gestor = current_user()
    if not gestor.pode_gerir(f):
        abort(403)
    if not f.ativo:
        flash("Funcionário inativo — reative antes de programar férias.", "erro")
        return redirect(url_for("funcionarios.detalhe", func_id=func_id))

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

    # Admin é isento do aviso prévio de 30 dias (registros de última hora /
    # acertos diretos com o colaborador); só não pode programar no passado.
    sem_aviso = gestor.is_admin
    data_minima = hoje if sem_aviso else hoje + timedelta(days=AVISO_PREVIO_DIAS)

    if form.validate_on_submit():
        periodo = db.session.get(PeriodoAquisitivo, form.periodo_id.data)
        erros = []

        if periodo is None or periodo.funcionario_id != f.id or periodo not in elegiveis:
            erros.append("Período inválido.")
        if form.data_inicio.data < data_minima:
            if sem_aviso:
                erros.append("A data de início não pode estar no passado.")
            else:
                erros.append(
                    f"As férias devem ser comunicadas com {AVISO_PREVIO_DIAS} dias de "
                    f"antecedência (a partir de {data_minima:%d/%m/%Y})."
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
                    criado_por_id=gestor.id,
                )
            )
            # Consome o saldo do período para evitar dupla programação.
            periodo.dias_restantes = (periodo.dias_restantes or 0) - dias
            db.session.commit()
            flash("Férias programadas com sucesso.", "ok")
            return redirect(url_for("funcionarios.detalhe", func_id=func_id))

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
        sem_aviso=sem_aviso,
    )


@bp.route("/<int:func_id>/programacoes/<int:prog_id>/cancelar", methods=["POST"])
@login_required
def cancelar(func_id, prog_id):
    hoje = date.today()
    f = db.get_or_404(Funcionario, func_id)
    if not current_user().pode_gerir(f):
        abort(403)
    prog = db.get_or_404(ProgramacaoFerias, prog_id)
    if prog.funcionario_id != f.id:
        abort(404)

    fim = prog.data_fim or prog.data_inicio
    if fim < hoje:
        flash(
            "Programação já encerrada — férias gozadas não podem ser canceladas.",
            "erro",
        )
        return redirect(url_for("funcionarios.detalhe", func_id=func_id))

    # Captura antes do delete: o commit expira a instância.
    data_inicio = prog.data_inicio

    # Devolve o saldo consumido na criação (manual) ou deduzido pela
    # fórmula da planilha (import). Período é nullable.
    restaurado = False
    if prog.periodo is not None:
        prog.periodo.dias_restantes = (
            prog.periodo.dias_restantes or 0
        ) + prog.dias_gozo
        restaurado = True

    db.session.delete(prog)
    db.session.commit()
    msg = f"Programação de {data_inicio:%d/%m/%Y} cancelada."
    if restaurado:
        msg += " Saldo do período restaurado."
    flash(msg, "ok")
    return redirect(url_for("funcionarios.detalhe", func_id=func_id))
