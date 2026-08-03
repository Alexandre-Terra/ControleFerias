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
from sqlalchemy.exc import IntegrityError

from ..auth import current_user, login_required
from ..forms import ProgramacaoForm
from ..models import Funcionario, PeriodoAquisitivo, ProgramacaoFerias, db
from .. import periodos as pf
from .. import status as st

bp = Blueprint("programacao", __name__, url_prefix="/funcionarios")

AVISO_PREVIO_DIAS = 30


def _periodos_elegiveis(funcionario, hoje):
    """Períodos fechados (fim <= hoje) com saldo derivado > 0.

    Mesma regra de "tem direito" de ``status.py``, sobre banco + janelas
    virtuais — o saldo é sempre o derivado, nunca a coluna congelada.
    """
    return [
        p
        for p in pf.periodos_efetivos(funcionario, hoje)
        if p.fim and p.fim <= hoje and st.saldo_periodo(funcionario, p, hoje) > 0
    ]


def _token(periodo):
    """Value do select: id do banco, ou ``v:<início ISO>`` para virtual."""
    if periodo.id is not None:
        return str(periodo.id)
    return f"v:{periodo.inicio.isoformat()}"


def _resolver_periodo(f, token, hoje):
    """Resolve o value do select num período do banco ou numa janela virtual.

    Janela virtual é RE-GERADA no servidor e casada pelo início — nunca se
    confia em datas vindas do client. Token virtual de janela já materializada
    (double-submit, outro worker) cai na linha existente do banco.
    """
    if token and token.startswith("v:"):
        try:
            inicio = date.fromisoformat(token[2:])
        except ValueError:
            return None
        existente = PeriodoAquisitivo.query.filter_by(
            funcionario_id=f.id, inicio=inicio
        ).first()
        if existente:
            return existente
        for janela in pf.janelas_virtuais(f, hoje):
            if janela.inicio == inicio:
                return janela
        return None
    try:
        pid = int(token)
    except (TypeError, ValueError):
        return None
    periodo = db.session.get(PeriodoAquisitivo, pid)
    if periodo is None or periodo.funcionario_id != f.id:
        return None
    return periodo


def _materializar(f, janela):
    """Cria a linha da janela virtual (``snapshot_em`` nulo = regime derivado).

    Idempotente pela unique ``funcionario_id + inicio`` — se outro worker
    materializou no meio do caminho, reaproveita a linha dele.
    """
    existente = PeriodoAquisitivo.query.filter_by(
        funcionario_id=f.id, inicio=janela.inicio
    ).first()
    if existente:
        return existente
    periodo = PeriodoAquisitivo(
        funcionario_id=f.id,
        inicio=janela.inicio,
        fim=janela.fim,
        limite_gozo=janela.limite_gozo,
    )
    db.session.add(periodo)
    db.session.flush()
    return periodo


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
            _token(p),
            f"{p.inicio:%d/%m/%Y} a {p.fim:%d/%m/%Y} "
            f"(saldo {st.saldo_periodo(f, p, hoje):g} dias"
            + (f", limite {p.limite_gozo:%d/%m/%Y}" if p.limite_gozo else "")
            + (" — novo período)" if p.id is None else ")"),
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
        periodo = _resolver_periodo(f, form.periodo_id.data, hoje)
        erros = []

        if periodo is None or not (periodo.fim and periodo.fim <= hoje):
            erros.append("Período inválido.")
            periodo = None
        if form.data_inicio.data < data_minima:
            if sem_aviso:
                erros.append("A data de início não pode estar no passado.")
            else:
                erros.append(
                    f"As férias devem ser comunicadas com {AVISO_PREVIO_DIAS} dias de "
                    f"antecedência (a partir de {data_minima:%d/%m/%Y})."
                )
        saldo_disponivel = st.saldo_periodo(f, periodo, hoje) if periodo else 0
        if periodo and form.dias_gozo.data > saldo_disponivel:
            erros.append(
                f"Dias de gozo ({form.dias_gozo.data}) excedem o saldo do período "
                f"({saldo_disponivel:g})."
            )

        if erros:
            for e in erros:
                flash(e, "erro")
        else:
            # Janela virtual só vira linha AQUI, com todas as validações
            # passadas — na mesma transação da programação.
            if periodo.id is None:
                periodo = _materializar(f, periodo)
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
            # Nada de debitar coluna: a própria linha criada consome o saldo
            # derivado (ver status.saldo_periodo).
            try:
                db.session.commit()
            except IntegrityError:
                # Corrida entre workers (período materializado em dobro) ou
                # programação duplicada na mesma data de início.
                db.session.rollback()
                flash(
                    "Não foi possível registrar — já existe programação nesta "
                    "data ou o registro foi feito em paralelo. Tente novamente.",
                    "erro",
                )
                return redirect(url_for("programacao.programar", func_id=func_id))
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

    # Apagar a linha já devolve o saldo (ele é derivado das programações
    # existentes); só a mensagem depende de haver período vinculado.
    restaurado = prog.periodo_aquisitivo_id is not None

    db.session.delete(prog)
    db.session.commit()
    msg = f"Programação de {data_inicio:%d/%m/%Y} cancelada."
    if restaurado:
        msg += " Saldo do período restaurado."
    flash(msg, "ok")
    return redirect(url_for("funcionarios.detalhe", func_id=func_id))
