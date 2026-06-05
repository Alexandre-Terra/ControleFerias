"""Lista de funcionários (filtros + busca + badge), detalhe e edição de setor."""
from datetime import date

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy.orm import joinedload

from ..auth import admin_required, current_user, filtrar_por_escopo, login_required
from ..models import Empresa, Funcionario, Setor, db
from .. import dashviz
from .. import status as st

bp = Blueprint("funcionarios", __name__, url_prefix="/funcionarios")

# Pseudo-filtro do painel: vencidas ∪ a vencer.
RISCO = "RISCO"
_RISCO_STATUS = (st.VENCIDA, st.A_VENCER)


@bp.route("/")
@login_required
def listar():
    hoje = date.today()
    dav = current_app.config["ALERTA_A_VENCER_DIAS"]

    empresa_id = request.args.get("empresa", type=int)
    setor_id = request.args.get("setor", type=int)
    status_filtro = request.args.get("status") or ""
    busca = (request.args.get("busca") or "").strip()

    # Carrega tudo (dentro do escopo do gestor) e calcula o status uma vez —
    # os chips mostram contagens do conjunto escopado.
    funcionarios = filtrar_por_escopo(
        Funcionario.query.options(
            joinedload(Funcionario.periodos),
            joinedload(Funcionario.programacoes),
            joinedload(Funcionario.empresa),
            joinedload(Funcionario.setor),
        ).order_by(Funcionario.nome),
        current_user(),
    ).all()

    todas = []
    chip_counts = {s: 0 for s in st.PRECEDENCIA}
    for f in funcionarios:
        agregado = st.status_funcionario(f, hoje, dav)
        chip_counts[agregado] += 1
        restantes = sum(
            (p.dias_restantes or 0)
            for p, s in st.periodos_com_status(f, hoje, dav)
            if s in (st.TEM_DIREITO, st.A_VENCER, st.VENCIDA)
        )
        todas.append({
            "f": f,
            "status": agregado,
            "restantes": restantes,
            "dias": dashviz.dias_para_limite(f, hoje, dav),
        })

    risco_count = sum(chip_counts[s] for s in _RISCO_STATUS)

    # Filtros (em Python, sobre o conjunto já calculado).
    linhas = todas
    if busca:
        b = busca.lower()
        linhas = [l for l in linhas
                  if b in l["f"].nome.lower() or b in (l["f"].codigo or "").lower()]
    if empresa_id:
        linhas = [l for l in linhas if l["f"].empresa_id == empresa_id]
    if setor_id:
        linhas = [l for l in linhas if l["f"].setor_id == setor_id]
    if status_filtro == RISCO:
        linhas = [l for l in linhas if l["status"] in _RISCO_STATUS]
    elif status_filtro:
        linhas = [l for l in linhas if l["status"] == status_filtro]

    linhas.sort(key=lambda l: (
        st.PRECEDENCIA.index(l["status"]),
        l["dias"] if l["dias"] is not None else 10 ** 9,
    ))

    return render_template(
        "funcionarios_list.html",
        linhas=linhas,
        total=len(todas),
        chip_counts=chip_counts,
        risco_count=risco_count,
        empresas=Empresa.query.order_by(Empresa.nome).all(),
        setores=Setor.query.order_by(Setor.nome).all(),
        status_opcoes=st.PRECEDENCIA,
        filtros={
            "empresa": empresa_id,
            "setor": setor_id,
            "status": status_filtro,
            "busca": busca,
        },
    )


@bp.route("/<int:func_id>")
@login_required
def detalhe(func_id):
    hoje = date.today()
    dav = current_app.config["ALERTA_A_VENCER_DIAS"]
    f = db.get_or_404(Funcionario, func_id)
    if not current_user().pode_gerir(f):
        abort(403)

    periodos = st.periodos_com_status(f, hoje, dav)
    return render_template(
        "funcionario_detail.html",
        f=f,
        periodos=periodos,
        agregado=st.status_funcionario(f, hoje, dav),
        tem_direito=st.tem_direito(f, hoje, dav),
        setores=Setor.query.order_by(Setor.nome).all(),
    )


@bp.route("/<int:func_id>/setor", methods=["POST"])
@admin_required
def definir_setor(func_id):
    f = db.get_or_404(Funcionario, func_id)
    setor_id = request.form.get("setor_id", type=int)
    f.setor_id = setor_id or None
    db.session.commit()
    flash("Setor atualizado.", "ok")
    return redirect(url_for("funcionarios.detalhe", func_id=func_id))
