"""Application factory."""
from datetime import date

from flask import Flask
from flask_migrate import Migrate

from .config import Config
from .models import db

migrate = Migrate()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)

    from . import auth, cli
    from .routes import dashboard, funcionarios, programacao

    app.register_blueprint(auth.bp)
    app.register_blueprint(cli.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(funcionarios.bp)
    app.register_blueprint(programacao.bp)

    from . import status as status_mod

    @app.context_processor
    def inject_globals():
        return {
            "STATUS_LABELS": status_mod.LABELS,
            "STATUS_BADGE": status_mod.BADGE,
            "hoje": date.today(),
        }

    return app
