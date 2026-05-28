"""Lista de funcionários (filtros + busca + badge), detalhe e edição de setor."""
from datetime import date

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy.orm import joinedload

from ..auth import login_required
from ..models import Empresa, Funcionario, Setor, db
from .. import status as st

bp = Blueprint("funcionarios", __name__, url_prefix="/funcionarios")


@bp.route("/")
@login_required
def listar():
    hoje = date.today()
    dav = current_app.config["ALERTA_A_VENCER_DIAS"]

    empresa_id = request.args.get("empresa", type=int)
    setor_id = request.args.get("setor", type=int)
    status_filtro = request.args.get("status") or ""
    busca = (request.args.get("busca") or "").strip()

    query = Funcionario.query.options(
        joinedload(Funcionario.periodos),
        joinedload(Funcionario.programacoes),
        joinedload(Funcionario.empresa),
        joinedload(Funcionario.setor),
    )
    if empresa_id:
        query = query.filter(Funcionario.empresa_id == empresa_id)
    if setor_id:
        query = query.filter(Funcionario.setor_id == setor_id)
    if busca:
        like = f"%{busca}%"
        query = query.filter(
            db.or_(Funcionario.nome.ilike(like), Funcionario.codigo.ilike(like))
        )

    funcionarios = query.order_by(Funcionario.nome).all()

    linhas = []
    for f in funcionarios:
        agregado = st.status_funcionario(f, hoje, dav)
        if status_filtro and agregado != status_filtro:
            continue
        restantes = sum(
            (p.dias_restantes or 0)
            for p, s in st.periodos_com_status(f, hoje, dav)
            if s in (st.TEM_DIREITO, st.A_VENCER, st.VENCIDA)
        )
        linhas.append({"f": f, "status": agregado, "restantes": restantes})

    return render_template(
        "funcionarios_list.html",
        linhas=linhas,
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
@login_required
def definir_setor(func_id):
    f = db.get_or_404(Funcionario, func_id)
    setor_id = request.form.get("setor_id", type=int)
    f.setor_id = setor_id or None
    db.session.commit()
    flash("Setor atualizado.", "ok")
    return redirect(url_for("funcionarios.detalhe", func_id=func_id))
