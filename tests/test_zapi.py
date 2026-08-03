"""Testes da integração WhatsApp (Z-API): digest, cliente, comando e HUD."""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
import requests

from app import zapi, zapi_digest
from app.models import (
    ConfiguracaoZapi,
    Empresa,
    EnvioZapi,
    Funcionario,
    PeriodoAquisitivo,
    ProgramacaoFerias,
    db,
)

HOJE = date(2026, 6, 23)


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #
@pytest.fixture
def empresa(app):
    e = Empresa(nome="ACME")
    db.session.add(e)
    db.session.commit()
    return e


def _funcionario(empresa, nome, codigo, *, fim, limite, restantes=30.0):
    f = Funcionario(empresa=empresa, codigo=codigo, nome=nome, ativo=True)
    db.session.add(f)
    db.session.flush()
    db.session.add(
        PeriodoAquisitivo(
            funcionario=f,
            inicio=(fim or HOJE) - timedelta(days=365),
            fim=fim,
            dias_direito=30,
            saldo_snapshot=restantes,
            # Fechados entram no regime snapshot (base = AG); o aberto segue
            # derivado (em formacao) — como na base real.
            snapshot_em=HOJE,
            limite_gozo=limite,
        )
    )
    db.session.commit()
    return f


def _config_pronta():
    cfg = ConfiguracaoZapi.obter()
    cfg.ativo = True
    cfg.base_url = "https://api.z-api.io"
    cfg.instance_id = "INST123"
    cfg.instance_token = "ITOKEN"
    cfg.client_token = "CTOKEN"
    cfg.destinatarios = "5511111111111\n5512222222222"
    cfg.hora_envio = 0
    cfg.apenas_dias_uteis = False
    cfg.enviar_se_vazio = True
    db.session.commit()
    return cfg


# --------------------------------------------------------------------------- #
# Digest
# --------------------------------------------------------------------------- #
def test_coletar_itens_filtra_por_regras(empresa):
    _funcionario(empresa, "Vencido", "1", fim=HOJE - timedelta(days=400),
                 limite=HOJE - timedelta(days=10))
    _funcionario(empresa, "A Vencer", "2", fim=HOJE - timedelta(days=100),
                 limite=HOJE + timedelta(days=20))
    _funcionario(empresa, "Tem Direito", "3", fim=HOJE - timedelta(days=100),
                 limite=HOJE + timedelta(days=300))
    _funcionario(empresa, "Em Formacao", "4", fim=HOJE + timedelta(days=100),
                 limite=HOJE + timedelta(days=465))

    cfg = ConfiguracaoZapi.obter()
    cfg.notificar_vencida = True
    cfg.notificar_a_vencer = True
    cfg.notificar_tem_direito = False
    cfg.antecedencia_dias = 60

    itens = zapi_digest.coletar_itens(HOJE, cfg)
    nomes = [it["nome"] for it in itens]

    assert nomes == ["Vencido", "A Vencer"]  # ordenado por precedência
    assert itens[0]["status"] == "VENCIDA"
    assert itens[1]["status"] == "A_VENCER"


def test_coletar_itens_ignora_inativo(empresa):
    f = _funcionario(empresa, "Vencido", "1", fim=HOJE - timedelta(days=400),
                     limite=HOJE - timedelta(days=10))
    f.ativo = False
    db.session.commit()

    cfg = ConfiguracaoZapi.obter()
    assert zapi_digest.coletar_itens(HOJE, cfg) == []


def test_destinatarios_validos_normaliza_e_deduplica(app):
    cfg = ConfiguracaoZapi.obter()
    cfg.destinatarios = "5511999999999\n+55 (11) 99999-9999\nabc\n\n5512222222222"
    db.session.commit()
    # os dois primeiros normalizam para o mesmo número; 'abc' é descartado
    assert cfg.destinatarios_validos() == ["5511999999999", "5512222222222"]


def test_montar_mensagem_render_seguro(app):
    cfg = ConfiguracaoZapi()
    cfg.modelo_cabecalho = "Resumo {data} — {total} item(ns)"
    cfg.modelo_linha = "{nome}|{status}|{desconhecida}|R$ {valor"
    cfg.modelo_sem_pendencias = "Nada em {data}"
    cfg.enviar_se_vazio = False

    itens = [{"nome": "Ana", "empresa": "ACME", "setor": "TI",
              "status_label": "Vencida", "dias": "30", "limite": "01/01/2026"}]
    msg = zapi_digest.montar_mensagem(cfg, itens, HOJE)

    assert "Resumo 23/06/2026 — 1 item(ns)" in msg
    assert "Ana|Vencida|" in msg
    assert "{desconhecida}" in msg     # chave desconhecida fica intacta
    assert "R$ {valor" in msg          # chave sem fechamento fica intacta


def test_montar_mensagem_vazio(app):
    cfg = ConfiguracaoZapi()
    cfg.modelo_sem_pendencias = "Tudo certo em {data}"
    cfg.enviar_se_vazio = False
    assert zapi_digest.montar_mensagem(cfg, [], HOJE) is None

    cfg.enviar_se_vazio = True
    assert zapi_digest.montar_mensagem(cfg, [], HOJE) == "Tudo certo em 23/06/2026"

    # forcar=True sempre devolve mensagem, mesmo com enviar_se_vazio off
    cfg.enviar_se_vazio = False
    assert zapi_digest.montar_mensagem(cfg, [], HOJE, forcar=True) is not None


# --------------------------------------------------------------------------- #
# Cliente HTTP
# --------------------------------------------------------------------------- #
class _FakeResp:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self._json = json_data
        self.text = text

    def json(self):
        if self._json is None:
            raise ValueError("sem json")
        return self._json


def _cfg_cliente():
    return SimpleNamespace(
        base_url="https://api.z-api.io",
        instance_id="INST123",
        instance_token="ITOKEN",
        client_token="CTOKEN",
    )


def test_enviar_texto_sucesso(monkeypatch):
    capturado = {}

    def fake_post(url, json, headers, timeout):
        capturado.update(url=url, json=json, headers=headers, timeout=timeout)
        return _FakeResp(200, {"zaapId": "Z1", "messageId": "M1"})

    monkeypatch.setattr(zapi.requests, "post", fake_post)
    ok, detalhe = zapi.enviar_texto(_cfg_cliente(), "+55 (11) 99999-9999", "oi")

    assert ok is True
    assert detalhe == "messageId=M1"
    assert "INST123" in capturado["url"] and "ITOKEN" in capturado["url"]
    assert capturado["url"].endswith("/send-text")
    assert capturado["headers"]["Client-Token"] == "CTOKEN"
    assert capturado["json"] == {"phone": "5511999999999", "message": "oi"}


def test_enviar_texto_telefone_invalido(monkeypatch):
    chamado = {"n": 0}
    monkeypatch.setattr(zapi.requests, "post",
                        lambda *a, **k: chamado.__setitem__("n", chamado["n"] + 1))
    ok, detalhe = zapi.enviar_texto(_cfg_cliente(), "123", "oi")
    assert ok is False
    assert "inválido" in detalhe.lower()
    assert chamado["n"] == 0  # nem chega a chamar a API


def test_enviar_texto_corpo_de_erro_com_200(monkeypatch):
    monkeypatch.setattr(zapi.requests, "post",
                        lambda *a, **k: _FakeResp(200, {"error": "x"}, text='{"error":"x"}'))
    ok, detalhe = zapi.enviar_texto(_cfg_cliente(), "5511999999999", "oi")
    assert ok is False
    assert "HTTP 200" in detalhe


def test_enviar_texto_excecao(monkeypatch):
    def boom(*a, **k):
        raise requests.exceptions.ConnectionError("sem rede")

    monkeypatch.setattr(zapi.requests, "post", boom)
    ok, detalhe = zapi.enviar_texto(_cfg_cliente(), "5511999999999", "oi")
    assert ok is False
    assert "conexão" in detalhe.lower()


def test_enviar_texto_nao_vaza_token(monkeypatch):
    vazado = "HTTP 401 token=ITOKEN client=CTOKEN"
    monkeypatch.setattr(zapi.requests, "post",
                        lambda *a, **k: _FakeResp(401, {"error": "auth"}, text=vazado))
    ok, detalhe = zapi.enviar_texto(_cfg_cliente(), "5511999999999", "oi")
    assert ok is False
    assert "ITOKEN" not in detalhe and "CTOKEN" not in detalhe
    assert "***" in detalhe


@pytest.mark.parametrize("entrada,esperado", [
    ("+55 (11) 99999-9999", "5511999999999"),
    ("11 3030-3030", "1130303030"),
    ("123", None),
    ("", None),
    (None, None),
])
def test_normalizar_telefone(entrada, esperado):
    assert zapi.normalizar_telefone(entrada) == esperado


# --------------------------------------------------------------------------- #
# Comando agendado (CLI)
# --------------------------------------------------------------------------- #
def test_cli_noop_quando_inativa(app, monkeypatch):
    chamadas = []
    monkeypatch.setattr(zapi, "enviar_texto",
                        lambda *a, **k: chamadas.append(a) or (True, "ok"))
    res = app.test_cli_runner().invoke(args=["enviar-alertas-zapi"])
    assert res.exit_code == 0
    assert "inativa ou incompleta" in res.output
    assert chamadas == []
    assert EnvioZapi.query.count() == 0


def test_cli_dry_run_nao_persiste(app, monkeypatch):
    _config_pronta()
    chamadas = []
    monkeypatch.setattr(zapi, "enviar_texto",
                        lambda *a, **k: chamadas.append(a) or (True, "ok"))
    res = app.test_cli_runner().invoke(args=["enviar-alertas-zapi", "--dry-run"])
    assert res.exit_code == 0
    assert "[DRY-RUN]" in res.output
    assert chamadas == []
    assert EnvioZapi.query.count() == 0


def test_cli_envia_e_anti_duplica(app, monkeypatch):
    _config_pronta()
    enviados = []
    monkeypatch.setattr(
        zapi, "enviar_texto",
        lambda cfg, numero, msg: (enviados.append(numero) or (True, "messageId=1")),
    )

    res = app.test_cli_runner().invoke(args=["enviar-alertas-zapi"])
    assert res.exit_code == 0
    db.session.expire_all()
    assert len(enviados) == 2
    assert EnvioZapi.query.filter_by(status="ok").count() == 2

    # segunda execução no mesmo dia: ambos já enviados → não reenvia
    res2 = app.test_cli_runner().invoke(args=["enviar-alertas-zapi"])
    assert res2.exit_code == 0
    assert len(enviados) == 2  # nenhum novo envio
    assert EnvioZapi.query.count() == 2


def test_cli_retry_de_falha_parcial(app, monkeypatch):
    _config_pronta()
    enviados = []

    def fake(cfg, numero, msg):
        enviados.append(numero)
        return (numero == "5511111111111", "messageId=1")

    monkeypatch.setattr(zapi, "enviar_texto", fake)

    app.test_cli_runner().invoke(args=["enviar-alertas-zapi"])
    db.session.expire_all()
    assert EnvioZapi.query.filter_by(status="ok").count() == 1
    assert EnvioZapi.query.filter_by(status="erro").count() == 1

    # nova execução: o que falhou é reenviado; o que deu ok é pulado
    enviados.clear()
    app.test_cli_runner().invoke(args=["enviar-alertas-zapi"])
    assert enviados == ["5512222222222"]


def test_cli_dedup_e_descarta_invalido(app, monkeypatch):
    cfg = _config_pronta()
    cfg.destinatarios = "5511999999999\n+55 11 99999-9999\nabc\n5512222222222"
    db.session.commit()
    enviados = []
    monkeypatch.setattr(
        zapi, "enviar_texto",
        lambda c, n, m: (enviados.append(n) or (True, "messageId=1")),
    )
    app.test_cli_runner().invoke(args=["enviar-alertas-zapi"])
    db.session.expire_all()
    # número repetido (formatos diferentes) envia uma vez; 'abc' é descartado
    assert sorted(enviados) == ["5511999999999", "5512222222222"]
    assert EnvioZapi.query.count() == 2


def test_cli_dry_run_ignora_gates(app, monkeypatch):
    cfg = _config_pronta()
    cfg.hora_envio = 23        # gate de hora ativo quase o dia todo
    cfg.apenas_dias_uteis = True
    db.session.commit()
    chamadas = []
    monkeypatch.setattr(zapi, "enviar_texto",
                        lambda *a, **k: chamadas.append(a) or (True, "ok"))
    res = app.test_cli_runner().invoke(args=["enviar-alertas-zapi", "--dry-run"])
    assert res.exit_code == 0
    assert "[DRY-RUN]" in res.output  # dry-run mostra o preview mesmo fora da janela
    assert chamadas == []
    assert EnvioZapi.query.count() == 0


# --------------------------------------------------------------------------- #
# HUD (admin)
# --------------------------------------------------------------------------- #
def test_hud_exige_admin(client_gestor):
    assert client_gestor.get("/integracoes/zapi/").status_code == 403


def test_hud_get_admin(client_admin):
    r = client_admin.get("/integracoes/zapi/")
    assert r.status_code == 200
    assert b"Z-API" in r.data or b"WhatsApp" in r.data


def test_hud_salva_e_token_em_branco_mantem(client_admin):
    base = {
        "base_url": "https://api.z-api.io",
        "instance_id": "INST",
        "client_token": "CLI1",
        "destinatarios": "5511999999999",
        "antecedencia_dias": "45",
        "hora_envio": "9",
        "notificar_vencida": "y",
    }
    r = client_admin.post("/integracoes/zapi/",
                          data={**base, "instance_token": "TOK1"})
    assert r.status_code == 302
    cfg = ConfiguracaoZapi.obter()
    assert cfg.instance_token == "TOK1"
    assert cfg.antecedencia_dias == 45
    assert cfg.notificar_vencida is True
    assert cfg.notificar_a_vencer is False  # checkbox ausente → False

    # POST sem o token → mantém o atual (masking / branco-mantém)
    r2 = client_admin.post("/integracoes/zapi/",
                           data={**base, "instance_token": ""})
    assert r2.status_code == 302
    db.session.expire_all()
    assert ConfiguracaoZapi.obter().instance_token == "TOK1"


def test_hud_testar_envia(client_admin, monkeypatch):
    cfg = ConfiguracaoZapi.obter()
    cfg.instance_id = "INST"
    cfg.instance_token = "TOK"
    cfg.client_token = "CLI"
    cfg.destinatarios = "5511999999999"
    db.session.commit()

    chamadas = []
    monkeypatch.setattr(zapi, "enviar_texto",
                        lambda c, n, m: (chamadas.append(n) or (True, "messageId=1")))
    r = client_admin.post("/integracoes/zapi/testar")
    assert r.status_code == 302
    assert chamadas == ["5511999999999"]
    db.session.expire_all()
    assert EnvioZapi.query.filter_by(tipo="teste", status="ok").count() == 1


def test_quando_local_converte_e_aceita_none(app):
    from datetime import datetime

    from app.routes.integracoes import _quando_local

    s = _quando_local(datetime(2026, 6, 23, 11, 0, 0))  # naive UTC
    assert "/" in s and ":" in s
    assert _quando_local(None) == "—"


def test_coletar_itens_usa_saldo_derivado(empresa):
    # Período que fechou DEPOIS do retrato (AG congelado 27,5) e com 10 dias
    # já gozados via app: o resumo tem de dizer 20 (30 − 10) — nem o valor
    # congelado, nem os 30 cheios.
    f = Funcionario(empresa=empresa, codigo="9", nome="Congelado", ativo=True)
    db.session.add(f)
    db.session.flush()
    p = PeriodoAquisitivo(
        funcionario=f,
        inicio=HOJE - timedelta(days=394),
        fim=HOJE - timedelta(days=30),
        dias_direito=27.5,
        saldo_snapshot=27.5,
        snapshot_em=HOJE - timedelta(days=60),  # retrato ANTES de fechar
        limite_gozo=HOJE + timedelta(days=300),
    )
    db.session.add(p)
    db.session.flush()
    db.session.add(ProgramacaoFerias(
        funcionario_id=f.id,
        periodo_aquisitivo_id=p.id,
        data_inicio=HOJE - timedelta(days=25),
        dias_gozo=10,
        data_fim=HOJE - timedelta(days=16),
        origem="manual",
    ))
    db.session.commit()

    cfg = _config_pronta()
    cfg.notificar_tem_direito = True
    db.session.commit()

    itens = zapi_digest.coletar_itens(HOJE, cfg)
    item = next(it for it in itens if it["nome"] == "Congelado")
    assert item["dias"] == "20"
