"""Autenticação por gestor identificado.

Cada gestor tem email + senha (hash). Status de login fica em ``session["user_id"]``.
O helper ``current_user()`` é a fonte da verdade dentro de uma request — re-busca
o gestor a cada chamada (o identity map do SQLAlchemy serve de cache barato) e
limpa a sessão se ele tiver sido desativado, garantindo que ``desativar gestor``
surte efeito imediato.
"""
from functools import wraps

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import false
from werkzeug.security import check_password_hash

from .forms import LoginForm
from .models import Funcionario, Gestor, db

bp = Blueprint("auth", __name__)


def filtrar_por_escopo(query, gestor):
    """Restringe uma query de ``Funcionario`` ao escopo do gestor.

    Admin: sem restrição. Gestor de setor: só o seu setor. Gestor não-admin
    sem setor: nada. Espelha ``Gestor.pode_gerir`` no nível de query —
    manter as duas em sincronia.
    """
    if gestor.is_admin:
        return query
    if gestor.setor_id is None:
        return query.filter(false())
    return query.filter(Funcionario.setor_id == gestor.setor_id)


def current_user():
    """Gestor ativo da sessão, ou ``None``.

    Se o gestor não existir mais ou estiver inativo, limpa a sessão.
    """
    user_id = session.get("user_id")
    if not user_id:
        return None

    gestor = db.session.get(Gestor, user_id)
    if gestor is None or not gestor.ativo:
        session.clear()
        return None

    return gestor


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        gestor = current_user()
        if gestor is None:
            return redirect(url_for("auth.login", next=request.path))
        if not gestor.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


@bp.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = (form.email.data or "").strip().lower()
        gestor = Gestor.query.filter_by(email=email).first()
        if (
            gestor
            and gestor.ativo
            and check_password_hash(gestor.senha_hash, form.senha.data)
        ):
            session.clear()
            session["user_id"] = gestor.id
            destino = request.args.get("next") or url_for("dashboard.index")
            return redirect(destino)
        flash("Email ou senha incorretos.", "erro")
    return render_template("login.html", form=form)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
