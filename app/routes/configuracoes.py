"""Configurações da conta do gestor logado (self-service).

Hub (`/configuracoes`) + troca da própria senha (`/configuracoes/senha`).
Diferente do reset do admin em `/gestores/<id>/senha`, aqui o gestor confirma
a identidade com a **senha atual** — conferida na rota (precisa do hash).
"""
from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from ..auth import current_user, login_required
from ..forms import AlterarSenhaForm
from ..models import db

bp = Blueprint("configuracoes", __name__, url_prefix="/configuracoes")


@bp.route("/")
@login_required
def index():
    return render_template("configuracoes.html")


@bp.route("/senha", methods=["GET", "POST"])
@login_required
def senha():
    gestor = current_user()
    form = AlterarSenhaForm()
    if form.validate_on_submit():
        if not check_password_hash(gestor.senha_hash, form.senha_atual.data):
            flash("Senha atual incorreta.", "erro")
        else:
            gestor.senha_hash = generate_password_hash(form.senha.data)
            db.session.commit()
            flash("Senha alterada.", "ok")
            return redirect(url_for("configuracoes.index"))
    return render_template("configuracoes_senha.html", form=form)
