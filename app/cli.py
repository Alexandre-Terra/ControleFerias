"""Comandos de linha de comando do Flask."""
import click
from flask import Blueprint
from werkzeug.security import generate_password_hash

from .importer import importar_xlsx
from .models import Gestor, db

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


@bp.cli.command("criar-gestor")
@click.option("--email", required=True, help="Email do gestor (usado para login).")
@click.option("--nome", required=True, help="Nome do gestor.")
@click.option("--senha", default=None, help="Senha (se omitida, será solicitada).")
@click.option("--admin", is_flag=True, help="Cria como administrador.")
def criar_gestor_command(email, nome, senha, admin):
    """Cria um gestor no banco. Use para o primeiro admin (bootstrap)."""
    email_norm = email.strip().lower()
    if Gestor.query.filter_by(email=email_norm).first():
        raise click.ClickException(f"Já existe um gestor com o email {email_norm}.")

    if not senha:
        senha = click.prompt(
            "Senha", hide_input=True, confirmation_prompt=True
        )
    if len(senha) < 6:
        raise click.ClickException("A senha precisa ter ao menos 6 caracteres.")

    g = Gestor(
        nome=nome.strip(),
        email=email_norm,
        senha_hash=generate_password_hash(senha),
        is_admin=admin,
        ativo=True,
    )
    db.session.add(g)
    db.session.commit()
    papel = "admin" if admin else "gestor"
    click.echo(f"Criado {papel} {g.nome} <{g.email}> (id={g.id}).")
