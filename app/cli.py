"""Comandos de linha de comando do Flask."""
import re
from datetime import date, datetime

import click
from flask import Blueprint, current_app
from sqlalchemy.orm import joinedload, selectinload

from werkzeug.security import generate_password_hash

from . import status
from .importer import importar_setores, importar_xlsx
from .models import Funcionario, Gestor, Setor, db

bp = Blueprint("cli", __name__, cli_group=None)


def _parse_data_br(valor):
    """dd/mm/aaaa (padrão do app) com fallback ISO; ``BadParameter`` se inválida."""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(valor, fmt).date()
        except ValueError:
            continue
    raise click.BadParameter(f"data inválida ({valor!r}) — use o formato dd/mm/aaaa.")


def _banco_alvo():
    """URI do banco com a senha mascarada — para o usuário conferir o destino."""
    uri = current_app.config["SQLALCHEMY_DATABASE_URI"]
    return re.sub(r"//([^:/@]+):[^@]+@", r"//\1:***@", uri)


def _echo_unicode_seguro(texto):
    """``click.echo`` resiliente à codificação do console (Windows cp1252).

    Modelos de mensagem podem ter emoji; ao imprimi-los (ex.: ``--dry-run``) num
    console que não é UTF-8, o ``click.echo`` cru levantaria ``UnicodeEncodeError``.
    Substitui o que não couber só na impressão — o envio real à Z-API usa
    JSON/UTF-8 e não passa por aqui.
    """
    import sys

    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    click.echo(texto.encode(enc, "replace").decode(enc))


@bp.cli.command("import-xlsx")
@click.argument("caminho")
@click.option(
    "--data-referencia",
    required=True,
    help=(
        "Data-retrato da planilha (dd/mm/aaaa): quando o AG foi calculado no "
        "Excel. Define o regime de saldo dos períodos — NÃO é a data de hoje."
    ),
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Simula a importação (rollback ao final) e mostra divergências.",
)
def import_xlsx_command(caminho, data_referencia, dry_run):
    """Importa a planilha (funcionários e períodos; programações nunca).

    Programações de férias nascem exclusivamente no app — a planilha é
    apenas a base de funcionários, períodos aquisitivos e saldos na
    data-retrato. O saldo atual é derivado (ver app/status.py).
    """
    from seeds.setores import seed_setores

    data_ref = _parse_data_br(data_referencia)

    if not dry_run:
        seed_setores()

    rel = importar_xlsx(caminho, data_ref, dry_run=dry_run)

    prefixo = "[DRY-RUN] " if dry_run else ""
    click.echo(f"{prefixo}Resultado da importação (retrato de {data_ref:%d/%m/%Y}):")
    for ent in ("empresas", "funcionarios", "periodos"):
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


@bp.cli.command("verificar-saldos")
@click.option(
    "--data",
    "data_str",
    default=None,
    help="Data de referência do cálculo (dd/mm/aaaa); padrão hoje.",
)
def verificar_saldos_command(data_str):
    """Confere o saldo derivado por período — só leitura, nada é gravado.

    Para cada funcionário ativo imprime período a período: regime (snapshot =
    AG da planilha vale como está; derivado = 30 ao fechar / proporcional em
    formação; virtual = janela ainda sem linha no banco), base, programado,
    saldo e status. No final, o resumo dos períodos que sobem para 30 e das
    janelas virtuais — instrumento de conferência antes/depois de deploy ou
    de import.
    """
    hoje = _parse_data_br(data_str) if data_str else date.today()
    dav = current_app.config["ALERTA_A_VENCER_DIAS"]
    click.echo(f"Banco: {_banco_alvo()}")
    click.echo(f"Referência: {hoje:%d/%m/%Y} (A vencer: limite em até {dav}d)\n")

    funcionarios = (
        Funcionario.query.filter(Funcionario.ativo.is_(True))
        .options(
            selectinload(Funcionario.periodos),
            selectinload(Funcionario.programacoes),
            joinedload(Funcionario.empresa),
        )
        .order_by(Funcionario.nome)
        .all()
    )

    subiram, virtuais, negativos = [], 0, []
    for f in funcionarios:
        _echo_unicode_seguro(f"{f.nome} ({f.empresa.nome if f.empresa else '—'})")
        for p, s, saldo in status.periodos_com_status(f, hoje, dav):
            if p.id is None:
                regime = "virtual"
                virtuais += 1
            elif status.fechado_no_snapshot(p):
                regime = "snapshot"
            else:
                regime = "derivado"
                if p.fim and p.fim <= hoje and p.snapshot_em is not None:
                    # Estava aberto no retrato e já fechou: é o caso que o
                    # cálculo antigo congelava (ex.: 27,5 em vez de 30).
                    subiram.append((f.nome, p))
            if saldo < 0:
                negativos.append((f.nome, p, saldo))
            base = status.base_periodo(p, hoje)
            programado = status.dias_programados(f, p)
            fim = f"{p.fim:%d/%m/%Y}" if p.fim else "—"
            _echo_unicode_seguro(
                f"  {p.inicio:%d/%m/%Y} a {fim}  [{regime:8s}] "
                f"base={base:g} programado={programado:g} saldo={saldo:g}  "
                f"{status.LABELS[s]}"
            )

    click.echo("\nResumo:")
    click.echo(f"  funcionarios ativos:          {len(funcionarios)}")
    click.echo(f"  fechados pos-retrato (-> 30): {len(subiram)}")
    click.echo(f"  janelas virtuais (sem linha): {virtuais}")
    if negativos:
        click.echo(
            "\nATENCAO - saldo negativo (dados inconsistentes; provavel dupla "
            "contagem entre planilha re-importada e programacoes do app):"
        )
        for nome, p, saldo in negativos:
            _echo_unicode_seguro(
                f"  {nome}: período {p.inicio:%d/%m/%Y} saldo={saldo:g}"
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
    click.echo(f"Banco alvo: {_banco_alvo()}")

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
@click.option(
    "--setor",
    default=None,
    help="Nome do setor a associar (gestor não-admin só gere o próprio setor).",
)
def criar_gestor_command(email, nome, senha, admin, setor):
    """Cria um gestor no banco. Use para o primeiro admin (bootstrap)."""
    email_norm = email.strip().lower()
    if Gestor.query.filter_by(email=email_norm).first():
        raise click.ClickException(f"Já existe um gestor com o email {email_norm}.")

    setor_obj = None
    if setor:
        setor_obj = Setor.query.filter_by(nome=setor.strip()).first()
        if setor_obj is None:
            raise click.ClickException(f"Setor '{setor.strip()}' não encontrado.")
    elif not admin:
        raise click.ClickException(
            "Gestor não-admin precisa de --setor (ou use --admin)."
        )

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
        setor_id=setor_obj.id if setor_obj else None,
        ativo=True,
    )
    db.session.add(g)
    db.session.commit()
    papel = "admin" if admin else f"gestor ({setor_obj.nome})"
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


@bp.cli.command("enviar-alertas-zapi")
@click.option(
    "--force",
    is_flag=True,
    help="Ignora os gates de hora/dia útil e a trava anti-duplicação.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Monta e imprime o resumo, sem enviar nem gravar.",
)
def enviar_alertas_zapi_command(force, dry_run):
    """Envia o resumo de férias por WhatsApp (Z-API) aos números configurados.

    Pensado para rodar de hora em hora por um cron: auto-restringe por
    ``hora_envio``/dia útil e por uma trava anti-duplicação **por destinatário**,
    disparando no máximo uma vez por dia por número. ``--force`` ignora os gates
    (usado em testes/validação); ``--dry-run`` só imprime, sem enviar/gravar.

    A configuração mora no banco (HUD do admin), não em variáveis de ambiente.
    """
    from . import zapi, zapi_digest
    from .models import ConfiguracaoZapi, EnvioZapi

    cfg = ConfiguracaoZapi.obter()
    if not cfg.pronta():
        click.echo(
            "zapi: integração inativa ou incompleta "
            "(sem credenciais/destinatários) — nada a fazer."
        )
        return

    agora = datetime.now()  # hora local — depende de TZ no ambiente do cron
    hoje = agora.date()

    # --dry-run é pré-visualização: ignora os gates de hora/dia (mas não envia).
    if not force and not dry_run:
        if cfg.apenas_dias_uteis and hoje.weekday() >= 5:
            click.echo("zapi: fim de semana (apenas_dias_uteis) — nada a fazer.")
            return
        if agora.hour < cfg.hora_envio:
            click.echo(
                f"zapi: antes da hora de envio ({cfg.hora_envio}h) — aguardando."
            )
            return

    itens = zapi_digest.coletar_itens(hoje, cfg)
    marcos = zapi_digest.coletar_marcos(hoje, cfg)
    mensagem = zapi_digest.montar_mensagem(cfg, itens, hoje, marcos=marcos)
    total = len(itens) + len(marcos)

    if mensagem is None:
        click.echo(
            f"zapi: sem pendências e enviar_se_vazio=off — nada a enviar "
            f"({total} itens)."
        )
        return

    destinatarios = cfg.destinatarios_validos()

    if dry_run:
        sep = "-" * 40
        _echo_unicode_seguro(
            f"[DRY-RUN] {total} item(ns). Mensagem:\n{sep}\n{mensagem}\n{sep}"
        )
        _echo_unicode_seguro(f"Destinatários: {', '.join(destinatarios)}")
        return

    # Anti-duplicação POR destinatário: pula quem já recebeu 'ok' agendado hoje.
    # Resolve dedup e retry de falha parcial numa regra só. --force reenvia tudo.
    enviados_ok = set()
    if not force:
        ja = EnvioZapi.query.filter_by(
            data_referencia=hoje, tipo="agendado", status="ok"
        ).all()
        enviados_ok = {e.destinatario for e in ja}

    enviados = falhas = pulados = 0
    for numero in destinatarios:
        if numero in enviados_ok:
            pulados += 1
            continue
        ok, detalhe = zapi.enviar_texto(cfg, numero, mensagem)
        db.session.add(
            EnvioZapi(
                data_referencia=hoje,
                tipo="agendado",
                destinatario=numero,
                status="ok" if ok else "erro",
                detalhe=detalhe,
                total_itens=total,
            )
        )
        if ok:
            enviados += 1
        else:
            falhas += 1
    db.session.commit()
    click.echo(
        f"zapi: {enviados} enviado(s), {falhas} falha(s), "
        f"{pulados} já enviado(s) hoje. ({total} itens)"
    )
