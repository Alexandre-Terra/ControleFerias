"""Comandos de linha de comando do Flask."""
import click
from flask import Blueprint

from .importer import importar_xlsx

bp = Blueprint("cli", __name__, cli_group=None)


@bp.cli.command("import-xlsx")
@click.argument("caminho")
def import_xlsx_command(caminho):
    """Importa a planilha de férias (idempotente)."""
    from seeds.setores import seed_setores

    seed_setores()
    stats = importar_xlsx(caminho)
    click.echo(
        "Importação concluída: "
        f"{stats['empresas']} empresas, "
        f"{stats['funcionarios']} funcionários, "
        f"{stats['periodos']} períodos, "
        f"{stats['programacoes']} programações."
    )


@bp.cli.command("seed-setores")
def seed_setores_command():
    """Cria os setores padrão."""
    from seeds.setores import seed_setores

    criados = seed_setores()
    click.echo(f"{criados} setores criados.")
