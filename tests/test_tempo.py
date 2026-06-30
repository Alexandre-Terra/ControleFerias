"""Testes dos marcos de tempo de serviço: lógica pura, digest e página admin."""
from datetime import date, timedelta

import pytest

from app import tempo, zapi_digest
from app.models import (
    ConfiguracaoZapi,
    Empresa,
    EnvioZapi,
    Funcionario,
    db,
)

HOJE = date(2026, 6, 30)


# --------------------------------------------------------------------------- #
# Lógica pura (app/tempo.py)
# --------------------------------------------------------------------------- #
def _so_alertas(data_admissao, hoje=HOJE):
    return {mk["label"] for mk in tempo.alertas_do_dia(data_admissao, hoje)}


def test_sem_admissao_nao_tem_marcos():
    assert tempo.marcos_proximos(None, HOJE) == []
    assert tempo.alertas_do_dia(None, HOJE) == []
    assert tempo.proximo_marco(None, HOJE) is None
    assert tempo.tempo_de_casa_dias(None, HOJE) is None


def test_aviso_45_dias_cinco_dias_antes():
    # 45 dias caem em HOJE+5; o aviso (5 dias antes) é hoje.
    adm = HOJE - timedelta(days=40)
    assert _so_alertas(adm) == {"45 dias"}
    mk = next(m for m in tempo.marcos_proximos(adm, HOJE) if m["label"] == "45 dias")
    assert mk["dias_faltam"] == 5
    assert mk["alertar_hoje"] is True


def test_aviso_90_dias_cinco_dias_antes():
    adm = HOJE - timedelta(days=85)
    assert _so_alertas(adm) == {"90 dias"}


def test_aviso_120_dias_no_mesmo_dia():
    adm = HOJE - timedelta(days=120)
    alertas = tempo.alertas_do_dia(adm, HOJE)
    assert {m["label"] for m in alertas} == {"120 dias"}
    assert alertas[0]["dias_faltam"] == 0  # avisa no próprio dia do marco


def test_aviso_um_ano_dois_dias_antes():
    # Aniversário de 1 ano em HOJE+2; aviso (2 dias antes) é hoje.
    adm = tempo._soma_anos(HOJE, -1) + timedelta(days=2)
    assert _so_alertas(adm) == {"1 ano"}


def test_aviso_aniversarios_sucessivos():
    # 6 anos de casa: aniversário em HOJE+2 → avisa hoje, rotulado "6 anos".
    adm = tempo._soma_anos(HOJE, -6) + timedelta(days=2)
    assert _so_alertas(adm) == {"6 anos"}


def test_sem_alerta_fora_do_dia_de_aviso():
    # 45 dias caem em HOJE+10 (aviso só em HOJE+5): nada hoje.
    adm = HOJE - timedelta(days=35)
    assert tempo.alertas_do_dia(adm, HOJE) == []


def test_proximo_marco_e_o_mais_proximo():
    adm = HOJE - timedelta(days=10)  # recém-admitido
    prox = tempo.proximo_marco(adm, HOJE)
    assert prox["label"] == "45 dias"
    assert prox["dias_faltam"] == 35


def test_soma_anos_ajusta_29_fev():
    assert tempo._soma_anos(date(2024, 2, 29), 1) == date(2025, 2, 28)
    assert tempo._soma_anos(date(2024, 2, 29), 4) == date(2028, 2, 29)


def test_descricao_tempo_casa():
    assert tempo.descricao_tempo_casa(None, HOJE) == "—"
    assert tempo.descricao_tempo_casa(HOJE, HOJE) == "admitido hoje"
    assert tempo.descricao_tempo_casa(HOJE + timedelta(days=3), HOJE) == "ainda não iniciou"
    assert tempo.descricao_tempo_casa(HOJE - timedelta(days=5), HOJE) == "5 dias"
    assert tempo.descricao_tempo_casa(date(2024, 6, 30), HOJE) == "2 anos"
    assert tempo.descricao_tempo_casa(date(2025, 3, 30), HOJE) == "1 ano, 3 meses"
    assert tempo.descricao_tempo_casa(date(2026, 3, 30), HOJE) == "3 meses"


# --------------------------------------------------------------------------- #
# Digest (zapi_digest.coletar_marcos / montar_mensagem)
# --------------------------------------------------------------------------- #
@pytest.fixture
def empresa(app):
    e = Empresa(nome="ACME")
    db.session.add(e)
    db.session.commit()
    return e


def _func(empresa, nome, codigo, *, admissao, ativo=True):
    f = Funcionario(
        empresa=empresa, codigo=codigo, nome=nome, ativo=ativo, data_admissao=admissao
    )
    db.session.add(f)
    db.session.commit()
    return f


def test_coletar_marcos_pega_aviso_do_dia(empresa):
    cfg = ConfiguracaoZapi.obter()  # notificar_tempo_servico default True
    _func(empresa, "Ana", "1", admissao=HOJE - timedelta(days=40))   # 45 dias hoje
    _func(empresa, "Bia", "2", admissao=HOJE - timedelta(days=10))   # nada hoje
    _func(empresa, "Léo", "3", admissao=None)                         # sem admissão

    marcos = zapi_digest.coletar_marcos(HOJE, cfg)
    assert [m["nome"] for m in marcos] == ["Ana"]
    assert marcos[0]["marco"] == "45 dias"
    assert marcos[0]["dias"] == 5


def test_coletar_marcos_respeita_toggle(empresa):
    cfg = ConfiguracaoZapi.obter()
    cfg.notificar_tempo_servico = False
    db.session.commit()
    _func(empresa, "Ana", "1", admissao=HOJE - timedelta(days=40))
    assert zapi_digest.coletar_marcos(HOJE, cfg) == []


def test_coletar_marcos_ignora_inativo(empresa):
    cfg = ConfiguracaoZapi.obter()
    _func(empresa, "Ana", "1", admissao=HOJE - timedelta(days=40), ativo=False)
    assert zapi_digest.coletar_marcos(HOJE, cfg) == []


def test_montar_mensagem_so_marcos(app):
    cfg = ConfiguracaoZapi()
    cfg.modelo_tempo_cabecalho = "Tempo {data} — {total}"
    cfg.modelo_tempo = "{nome}|{marco}|{data}|{dias}"
    cfg.enviar_se_vazio = False
    marcos = [{"nome": "Ana", "empresa": "ACME", "setor": "TI",
               "marco": "45 dias", "data": "05/07/2026", "dias": 5}]
    # Sem férias, mas com marcos → mensagem (não None) só com o bloco de tempo.
    msg = zapi_digest.montar_mensagem(cfg, [], HOJE, marcos=marcos)
    assert "Tempo 30/06/2026 — 1" in msg
    assert "Ana|45 dias|05/07/2026|5" in msg


def test_montar_mensagem_ferias_e_marcos_juntos(app):
    cfg = ConfiguracaoZapi()
    cfg.modelo_cabecalho = "Férias {total}"
    cfg.modelo_linha = "F:{nome}"
    cfg.modelo_tempo_cabecalho = "Tempo {total}"
    cfg.modelo_tempo = "T:{nome}"
    itens = [{"nome": "Ana", "empresa": "ACME", "setor": "TI",
              "status_label": "Vencida", "dias": "30", "limite": "01/01/2026"}]
    marcos = [{"nome": "Bia", "empresa": "ACME", "setor": "TI",
               "marco": "1 ano", "data": "02/07/2026", "dias": 2}]
    msg = zapi_digest.montar_mensagem(cfg, itens, HOJE, marcos=marcos)
    assert "F:Ana" in msg and "T:Bia" in msg
    assert msg.index("F:Ana") < msg.index("T:Bia")  # férias antes de tempo


# --------------------------------------------------------------------------- #
# Comando agendado inclui os marcos
# --------------------------------------------------------------------------- #
def test_cli_envia_marco_do_dia(app, empresa, monkeypatch):
    from app import zapi

    cfg = ConfiguracaoZapi.obter()
    cfg.ativo = True
    cfg.instance_id = "INST"
    cfg.instance_token = "ITOK"
    cfg.client_token = "CTOK"
    cfg.destinatarios = "5511999999999"
    cfg.hora_envio = 0
    cfg.apenas_dias_uteis = False
    cfg.enviar_se_vazio = False  # sem marcos não enviaria
    db.session.commit()
    # Admissão relativa ao dia real (o comando usa date.today()).
    _func(empresa, "Ana", "1", admissao=date.today() - timedelta(days=40))

    capturadas = []
    monkeypatch.setattr(
        zapi, "enviar_texto",
        lambda c, n, m: (capturadas.append(m) or (True, "messageId=1")),
    )
    res = app.test_cli_runner().invoke(args=["enviar-alertas-zapi"])
    assert res.exit_code == 0
    assert len(capturadas) == 1
    assert "45 dias" in capturadas[0]
    assert EnvioZapi.query.filter_by(status="ok").count() == 1


# --------------------------------------------------------------------------- #
# Página admin
# --------------------------------------------------------------------------- #
def test_pagina_exige_admin(client_gestor):
    assert client_gestor.get("/tempo-funcionarios/").status_code == 403


def test_pagina_lista_e_destaca_aviso(client_admin, app):
    e = Empresa(nome="ACME")
    db.session.add(e)
    db.session.commit()
    _func(e, "Ana Aviso", "1", admissao=date.today() - timedelta(days=40))
    _func(e, "Bia Tranquila", "2", admissao=date.today() - timedelta(days=5))

    r = client_admin.get("/tempo-funcionarios/")
    assert r.status_code == 200
    assert "Ana Aviso".encode() in r.data
    assert "Bia Tranquila".encode() in r.data
    assert "45 dias".encode() in r.data
