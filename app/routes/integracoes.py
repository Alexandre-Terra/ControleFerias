"""HUD de integrações — configuração da Z-API (WhatsApp). Apenas admin.

A configuração da integração mora no banco (singleton ``ConfiguracaoZapi``),
editada inteiramente por esta tela — credenciais, modelos de mensagem e regras
de disparo. O envio agendado é feito pelo comando ``flask enviar-alertas-zapi``
(cron); aqui o admin configura e dispara um envio de **teste** para validar.
"""
from datetime import date, timezone

from flask import Blueprint, flash, redirect, render_template, url_for

from .. import zapi, zapi_digest
from ..auth import admin_required, current_user
from ..forms import ConfiguracaoZapiForm, TestarEnvioZapiForm
from ..models import ConfiguracaoZapi, EnvioZapi, db

bp = Blueprint("integracoes", __name__, url_prefix="/integracoes/zapi")

DEFAULT_BASE_URL = "https://api.z-api.io"


def _quando_local(dt):
    """Formata um ``criado_em`` (UTC) na hora local, coerente com o gate do cron."""
    if dt is None:
        return "—"
    aware = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    return aware.astimezone().strftime("%d/%m %H:%M")


@bp.route("/", methods=["GET", "POST"])
@admin_required
def zapi_config():
    cfg = ConfiguracaoZapi.obter()
    form = ConfiguracaoZapiForm(obj=cfg)
    if form.validate_on_submit():
        cfg.ativo = form.ativo.data
        cfg.base_url = (form.base_url.data or "").strip() or DEFAULT_BASE_URL
        cfg.instance_id = (form.instance_id.data or "").strip() or None
        # Tokens: em branco MANTÉM o atual (masking — mesmo padrão da senha em
        # GestorForm). O PasswordField nunca re-renderiza o valor salvo.
        if form.instance_token.data:
            cfg.instance_token = form.instance_token.data.strip()
        if form.client_token.data:
            cfg.client_token = form.client_token.data.strip()
        cfg.destinatarios = form.destinatarios.data or None
        cfg.notificar_vencida = form.notificar_vencida.data
        cfg.notificar_a_vencer = form.notificar_a_vencer.data
        cfg.notificar_tem_direito = form.notificar_tem_direito.data
        cfg.notificar_tempo_servico = form.notificar_tempo_servico.data
        cfg.antecedencia_dias = form.antecedencia_dias.data
        cfg.hora_envio = form.hora_envio.data
        cfg.apenas_dias_uteis = form.apenas_dias_uteis.data
        cfg.enviar_se_vazio = form.enviar_se_vazio.data
        # Modelo em branco mantém o atual (evita mensagem sem cabeçalho/linha).
        cfg.modelo_cabecalho = form.modelo_cabecalho.data or cfg.modelo_cabecalho
        cfg.modelo_linha = form.modelo_linha.data or cfg.modelo_linha
        cfg.modelo_sem_pendencias = (
            form.modelo_sem_pendencias.data or cfg.modelo_sem_pendencias
        )
        cfg.modelo_tempo_cabecalho = (
            form.modelo_tempo_cabecalho.data or cfg.modelo_tempo_cabecalho
        )
        cfg.modelo_tempo = form.modelo_tempo.data or cfg.modelo_tempo
        cfg.atualizado_por_id = current_user().id
        db.session.commit()
        flash("Configuração da Z-API salva.", "ok")
        return redirect(url_for("integracoes.zapi_config"))

    envios = EnvioZapi.query.order_by(EnvioZapi.criado_em.desc()).limit(15).all()
    for e in envios:  # hora local p/ exibição (criado_em é UTC) — atributo transiente
        e.quando = _quando_local(e.criado_em)
    return render_template(
        "integracoes_zapi.html",
        form=form,
        cfg=cfg,
        envios=envios,
        testar_form=TestarEnvioZapiForm(),
    )


@bp.route("/testar", methods=["POST"])
@admin_required
def zapi_testar():
    """Dispara um envio de teste aos números configurados (usa a config salva)."""
    if not TestarEnvioZapiForm().validate_on_submit():
        flash("Falha ao validar o formulário.", "erro")
        return redirect(url_for("integracoes.zapi_config"))

    cfg = ConfiguracaoZapi.obter()
    if not cfg.credenciais_ok() or not cfg.destinatarios_validos():
        flash(
            "Preencha as credenciais e ao menos um destinatário válido (e salve) "
            "antes de testar.",
            "erro",
        )
        return redirect(url_for("integracoes.zapi_config"))

    hoje = date.today()
    itens = zapi_digest.coletar_itens(hoje, cfg)
    marcos = zapi_digest.coletar_marcos(hoje, cfg)
    mensagem = zapi_digest.montar_mensagem(cfg, itens, hoje, marcos=marcos, forcar=True)

    enviados = falhas = 0
    for numero in cfg.destinatarios_validos():
        ok, detalhe = zapi.enviar_texto(cfg, numero, mensagem)
        db.session.add(
            EnvioZapi(
                data_referencia=hoje,
                tipo="teste",
                destinatario=numero,
                status="ok" if ok else "erro",
                detalhe=detalhe,
                total_itens=len(itens) + len(marcos),
            )
        )
        if ok:
            enviados += 1
        else:
            falhas += 1
    db.session.commit()

    if falhas == 0:
        flash(f"Teste enviado a {enviados} número(s).", "ok")
    else:
        flash(
            f"Teste: {enviados} enviado(s), {falhas} falha(s). "
            "Veja o histórico abaixo para o detalhe.",
            "erro",
        )
    return redirect(url_for("integracoes.zapi_config"))
