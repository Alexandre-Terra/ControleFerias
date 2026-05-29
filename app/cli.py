"""Comandos de linha de comando do Flask."""
import click
from flask import Blueprint

from .importer import importar_xlsx

bp = Blueprint("cli", __name__, cli_group=None)


@bp.cli.command("import-xlsx")
@click.argument("caminho")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Simula a importação (rollback ao final) e mostra divergências.",
)
def import_xlsx_command(caminho, dry_run):
    """Importa a planilha de férias (idempotente)."""
    from seeds.setores import seed_setores

    if not dry_run:
        seed_setores()

    rel = importar_xlsx(caminho, dry_run=dry_run)

    prefixo = "[DRY-RUN] " if dry_run else ""
    click.echo(f"{prefixo}Resultado da importação:")
    for ent in ("empresas", "funcionarios", "periodos", "programacoes"):
        c = rel[ent]
        click.echo(
            f"  {ent:14s} novos={c['novos']:4d}  "
            f"atualizados={c['atualizados']:4d}  "
            f"inalterados={c['inalterados']:4d}"
        )

    if rel["avisos"]:
        click.echo(f"\nDivergências ({len(rel['avisos'])}):")
        for a in rel["avisos"]:
            click.echo(f"  - {a}")
    else:
        click.echo("\nSem divergências.")

    if dry_run:
        click.echo(
            "\nNada foi gravado (dry-run). "
            "Rode novamente sem --dry-run para persistir."
        )


@bp.cli.command("seed-setores")
def seed_setores_command():
    """Cria os setores padrão."""
    from seeds.setores import seed_setores

    criados = seed_setores()
    click.echo(f"{criados} setores criados.")
