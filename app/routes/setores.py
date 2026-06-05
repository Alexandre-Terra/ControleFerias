"""Administração de setores (CRUD básico, apenas para admin).

Setor é global (compartilhado entre as empresas). Exclusão é bloqueada
enquanto houver funcionários (ativos ou inativos) ou gestores associados —
um vínculo pendente quebraria a FK no Postgres. Para corrigir nome, renomear.
"""
from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from ..auth import admin_required
from ..forms import SetorForm
from ..models import Funcionario, Gestor, Setor, db

bp = Blueprint("setores", __name__, url_prefix="/setores")


def _contagens():
    """{setor_id: (n_funcionarios, n_gestores)} — funcionários incluem inativos."""
    cont = {}
    for s in Setor.query.all():
        n_func = Funcionario.query.filter_by(setor_id=s.id).count()
        n_gest = Gestor.query.filter_by(setor_id=s.id).count()
        cont[s.id] = (n_func, n_gest)
    return cont


@bp.route("/")
@admin_required
def listar():
    setores = Setor.query.order_by(Setor.nome).all()
    return render_template(
        "setores_list.html", setores=setores, contagens=_contagens(), form=SetorForm()
    )


@bp.route("/novo", methods=["POST"])
@admin_required
def novo():
    form = SetorForm()
    if form.validate_on_submit():
        nome = form.nome.data.strip()
        if Setor.query.filter_by(nome=nome).first():
            flash("Já existe um setor com esse nome.", "erro")
        else:
            db.session.add(Setor(nome=nome))
            db.session.commit()
            flash(f"Setor {nome} criado.", "ok")
            return redirect(url_for("setores.listar"))
    setores = Setor.query.order_by(Setor.nome).all()
    return render_template(
        "setores_list.html", setores=setores, contagens=_contagens(), form=form
    )


@bp.route("/<int:setor_id>/renomear", methods=["POST"])
@admin_required
def renomear(setor_id):
    s = db.get_or_404(Setor, setor_id)
    nome = (request.form.get("nome") or "").strip()
    if not nome:
        flash("Nome não pode ficar em branco.", "erro")
    elif Setor.query.filter(Setor.nome == nome, Setor.id != s.id).first():
        flash("Já existe um setor com esse nome.", "erro")
    else:
        s.nome = nome
        db.session.commit()
        flash("Setor renomeado.", "ok")
    return redirect(url_for("setores.listar"))


@bp.route("/<int:setor_id>/excluir", methods=["POST"])
@admin_required
def excluir(setor_id):
    s = db.get_or_404(Setor, setor_id)
    n_func = Funcionario.query.filter_by(setor_id=s.id).count()
    n_gest = Gestor.query.filter_by(setor_id=s.id).count()
    if n_func or n_gest:
        flash(
            f"Setor em uso por {n_func} funcionário(s) / {n_gest} gestor(es) — "
            "reatribua antes de excluir.",
            "erro",
        )
    else:
        nome = s.nome
        db.session.delete(s)
        db.session.commit()
        flash(f"Setor {nome} excluído.", "ok")
    return redirect(url_for("setores.listar"))
