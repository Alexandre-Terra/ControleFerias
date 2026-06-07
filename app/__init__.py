"""Application factory."""
from datetime import date

from flask import Flask
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect

from .config import Config
from .models import db

migrate = Migrate()
csrf = CSRFProtect()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    from . import auth, cli
    from .routes import (
        configuracoes,
        dashboard,
        funcionarios,
        gestores,
        programacao,
        setores,
    )

    app.register_blueprint(auth.bp)
    app.register_blueprint(cli.bp)
    app.register_blueprint(configuracoes.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(funcionarios.bp)
    app.register_blueprint(gestores.bp)
    app.register_blueprint(programacao.bp)
    app.register_blueprint(setores.bp)

    # Rotas POST sem Flask-WTF (ferramenta interna, documentado no README/CLAUDE).
    csrf.exempt(app.view_functions["auth.logout"])
    csrf.exempt(app.view_functions["funcionarios.definir_setor"])

    from . import status as status_mod
    from . import uihelpers
    from .icons import ICONS

    @app.context_processor
    def inject_globals():
        return {
            "STATUS_LABELS": status_mod.LABELS,
            "STATUS_CLASS": status_mod.CLASS,
            "STATUS_VAR": status_mod.VAR,
            "ICONS": ICONS,
            "iniciais": uihelpers.iniciais,
            "avatar_cor": uihelpers.avatar_cor,
            "hoje": date.today(),
            "current_user": auth.current_user(),
        }

    return app
