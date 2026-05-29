"""Administração de gestores (CRUD básico, apenas para admin)."""
from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    url_for,
)
from werkzeug.security import generate_password_hash

from ..auth import admin_required, current_user
from ..forms import GestorForm, MudarSenhaForm
from ..models import Gestor, db

bp = Blueprint("gestores", __name__, url_prefix="/gestores")


@bp.route("/")
@admin_required
def listar():
    gestores = Gestor.query.order_by(Gestor.ativo.desc(), Gestor.nome).all()
    return render_template("gestores_list.html", gestores=gestores)


@bp.route("/novo", methods=["GET", "POST"])
@admin_required
def novo():
    form = GestorForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        if Gestor.query.filter_by(email=email).first():
            flash("Já existe um gestor com esse email.", "erro")
        elif not form.senha.data:
            flash("Senha é obrigatória ao criar um novo gestor.", "erro")
        else:
            g = Gestor(
                nome=form.nome.data.strip(),
                email=email,
                senha_hash=generate_password_hash(form.senha.data),
                is_admin=bool(form.is_admin.data),
                ativo=True,
            )
            db.session.add(g)
            db.session.commit()
            flash(f"Gestor {g.nome} criado.", "ok")
            return redirect(url_for("gestores.listar"))
    return render_template("gestor_form.html", form=form, modo="novo")


@bp.route("/<int:gestor_id>/desativar", methods=["POST"])
@admin_required
def desativar(gestor_id):
    g = db.get_or_404(Gestor, gestor_id)
    if g.id == current_user().id:
        flash("Você não pode desativar a si mesmo.", "erro")
    else:
        g.ativo = False
        db.session.commit()
        flash(f"Gestor {g.nome} desativado.", "ok")
    return redirect(url_for("gestores.listar"))


@bp.route("/<int:gestor_id>/reativar", methods=["POST"])
@admin_required
def reativar(gestor_id):
    g = db.get_or_404(Gestor, gestor_id)
    g.ativo = True
    db.session.commit()
    flash(f"Gestor {g.nome} reativado.", "ok")
    return redirect(url_for("gestores.listar"))


@bp.route("/<int:gestor_id>/senha", methods=["GET", "POST"])
@admin_required
def mudar_senha(gestor_id):
    g = db.get_or_404(Gestor, gestor_id)
    form = MudarSenhaForm()
    if form.validate_on_submit():
        g.senha_hash = generate_password_hash(form.senha.data)
        db.session.commit()
        flash(f"Senha de {g.nome} alterada.", "ok")
        return redirect(url_for("gestores.listar"))
    return render_template("gestor_senha.html", form=form, gestor=g)
