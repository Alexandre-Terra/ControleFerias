"""Autenticação por senha única (login compartilhado).

Gancho para evolução futura: trocar a checagem de senha única por usuários
com perfis por empresa/setor.
"""
from functools import wraps

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .forms import LoginForm

bp = Blueprint("auth", __name__)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("auth"):
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@bp.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        if form.senha.data == current_app.config["APP_PASSWORD"]:
            session["auth"] = True
            destino = request.args.get("next") or url_for("dashboard.index")
            return redirect(destino)
        flash("Senha incorreta.", "erro")
    return render_template("login.html", form=form)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
