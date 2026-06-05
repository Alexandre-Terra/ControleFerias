"""Comandos de linha de comando do Flask."""
import click
from flask import Blueprint, current_app
from werkzeug.security import generate_password_hash

from .importer import importar_setores, importar_xlsx
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


@bp.cli.command("import-setores")
@click.argument("caminho")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Simula (rollback ao final) e mostra o que mudaria.",
)
def import_setores_command(caminho, dry_run):
    """Atribui setores aos funcionários a partir da coluna B da planilha.

    Idempotente; casa por empresa (aba) + código. Os funcionários já devem
    existir — rode ``import-xlsx`` antes.
    """
    rel = importar_setores(caminho, dry_run=dry_run)

    prefixo = "[DRY-RUN] " if dry_run else ""
    click.echo(f"{prefixo}Importação de setores:")
    click.echo(f"  setores_criados = {rel['setores_criados']:4d}")
    click.echo(f"  atribuidos      = {rel['atribuidos']:4d}")
    click.echo(f"  inalterados     = {rel['inalterados']:4d}")
    click.echo(f"  sem_setor       = {rel['sem_setor']:4d}")

    if rel["nao_encontrados"]:
        click.echo(
            f"\nFuncionários não encontrados no banco "
            f"({len(rel['nao_encontrados'])}):"
        )
        for n in rel["nao_encontrados"]:
            click.echo(f"  - {n}")
        click.echo("  Rode 'flask import-xlsx' antes para criar os funcionários.")

    if rel["avisos"]:
        click.echo(f"\nAvisos ({len(rel['avisos'])}):")
        for a in rel["avisos"]:
            click.echo(f"  - {a}")

    if not rel["nao_encontrados"] and not rel["avisos"]:
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


@bp.cli.command("bootstrap-admin")
def bootstrap_admin_command():
    """Garante um admin a partir de ADMIN_EMAIL/ADMIN_SENHA (idempotente).

    Pensado para rodar no deploy (parte do startCommand), depois do
    ``flask db upgrade``. Comportamento:

    - Sem ADMIN_EMAIL ou ADMIN_SENHA → no-op (exit 0). Permite subir o app
      antes de configurar o admin; honra "sem senha padrão fixa".
    - Variáveis setadas mas inválidas (senha curta) → falha (exit != 0), para
      bloquear o deploy e evitar travar fora sem perceber.
    - Admin já existe → sincroniza a senha e reativa/promove (ativo + is_admin).
    - Admin não existe → cria.
    """
    email = (current_app.config.get("ADMIN_EMAIL") or "").strip().lower()
    senha = current_app.config.get("ADMIN_SENHA") or ""
    nome = (current_app.config.get("ADMIN_NOME") or "Administrador").strip()

    if not email or not senha:
        click.echo(
            "bootstrap-admin: ADMIN_EMAIL/ADMIN_SENHA não configurados — "
            "nada a fazer."
        )
        return

    if len(senha) < 6:
        raise click.ClickException(
            "bootstrap-admin: ADMIN_SENHA precisa ter ao menos 6 caracteres. "
            "Corrija a variável de ambiente e refaça o deploy."
        )

    senha_hash = generate_password_hash(senha)
    g = Gestor.query.filter_by(email=email).first()
    if g is None:
        g = Gestor(
            nome=nome,
            email=email,
            senha_hash=senha_hash,
            is_admin=True,
            ativo=True,
        )
        db.session.add(g)
        db.session.commit()
        click.echo(f"bootstrap-admin: admin criado <{email}> (id={g.id}).")
    else:
        g.senha_hash = senha_hash
        g.is_admin = True
        g.ativo = True
        db.session.commit()
        click.echo(
            f"bootstrap-admin: admin <{email}> sincronizado "
            "(senha redefinida, ativo, is_admin)."
        )
