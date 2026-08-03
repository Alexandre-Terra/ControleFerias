"""Testes dos marcos de tempo de serviço: lógica pura, digest e página admin."""
from datetime import date, timedelta

import pytest

from app import tempo, zapi_digest
from app.models import (
    ConfiguracaoZapi,
    Empresa,
    EnvioZapi,
    Funcionario,
    Setor,
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
# Marcos já batidos e janelas (app/tempo.py)
# --------------------------------------------------------------------------- #
def test_ultimo_marco_e_o_mais_recente_ja_atingido():
    # 100 dias de casa: 45 e 90 já passaram, 120 ainda não.
    mk = tempo.ultimo_marco(HOJE - timedelta(days=100), HOJE)
    assert mk["label"] == "90 dias"
    assert mk["chave"] == "90"
    assert mk["batido"] is True
    assert mk["dias_faltam"] == -10          # negativo: ficou para trás


def test_ultimo_marco_pode_ser_aniversario():
    # 1 ano e 2 meses de casa: o aniversário é mais recente que o marco de 120.
    adm = tempo._soma_anos(HOJE, -1) - timedelta(days=60)
    assert tempo.ultimo_marco(adm, HOJE)["label"] == "1 ano"


def test_ultimo_marco_none_antes_dos_45_dias():
    assert tempo.ultimo_marco(HOJE - timedelta(days=10), HOJE) is None
    assert tempo.ultimo_marco(None, HOJE) is None
    assert tempo.ultimo_marco(HOJE + timedelta(days=5), HOJE) is None


def test_ultimo_marco_conta_aniversario_de_29_fev():
    # Admissão em 29/02: o marco de 1 ano cai em 28/02 do ano seguinte e já
    # conta como batido nesse dia (a diferença de calendário diria "0 anos").
    assert tempo.ultimo_marco(date(2024, 2, 29), date(2025, 2, 28))["label"] == "1 ano"


def test_marcos_no_intervalo_pega_dias_e_aniversario():
    ini, fim = tempo.janela_mes(HOJE)                      # junho/2026
    # 45 dias cai em 30/06 (hoje); 90 dias só em agosto.
    marcos = tempo.marcos_no_intervalo(date(2026, 5, 16), ini, fim, HOJE)
    assert [mk["label"] for mk in marcos] == ["45 dias"]
    assert marcos[0]["batido"] is True

    # aniversário de 6 anos em 10/06/2026, dentro da janela
    marcos = tempo.marcos_no_intervalo(date(2020, 6, 10), ini, fim, HOJE)
    assert [mk["label"] for mk in marcos] == ["6 anos"]


def test_marcos_no_intervalo_vazio_e_ordenado():
    ini, fim = tempo.janela_mes(HOJE)
    assert tempo.marcos_no_intervalo(date(2026, 5, 20), ini, fim, HOJE) == []
    assert tempo.marcos_no_intervalo(None, ini, fim, HOJE) == []

    # Janela larga: todos os aniversários entram, em ordem (não só o próximo).
    marcos = tempo.marcos_no_intervalo(
        date(2020, 6, 10), date(2024, 1, 1), date(2026, 12, 31), HOJE
    )
    assert [mk["label"] for mk in marcos] == ["4 anos", "5 anos", "6 anos"]


def test_resumo_marcos_separa_batidos_de_a_bater():
    ini, fim = tempo.janela_mes(HOJE)
    marcos = (
        tempo.marcos_no_intervalo(date(2026, 5, 16), ini, fim, HOJE)   # 45, batido
        + tempo.marcos_no_intervalo(date(2020, 6, 10), ini, fim, HOJE)  # aniv., batido
        + tempo.marcos_no_intervalo(date(2026, 3, 3), ini, fim, HOJE)   # 90, batido
    )
    resumo = tempo.resumo_marcos(marcos)
    assert (resumo["total"], resumo["batidos"], resumo["a_bater"]) == (3, 3, 0)
    assert resumo["por_chave"]["45"] == {"total": 1, "batidos": 1, "a_bater": 0}
    assert resumo["por_chave"]["120"] == {"total": 0, "batidos": 0, "a_bater": 0}

    # Um marco futuro na janela do mês que vem entra como "a bater"
    # (admitido em 01/06 → 45 dias em 16/07).
    ini2, fim2 = tempo.janela_mes(tempo.desloca_mes(HOJE, 1))
    futuros = tempo.marcos_no_intervalo(date(2026, 6, 1), ini2, fim2, HOJE)
    r2 = tempo.resumo_marcos(futuros)
    assert (r2["total"], r2["batidos"], r2["a_bater"]) == (1, 0, 1)
    assert tempo.resumo_marcos([])["total"] == 0


def test_descricao_desde():
    assert tempo.descricao_desde(HOJE, HOJE) == "hoje"
    assert tempo.descricao_desde(HOJE - timedelta(days=12), HOJE) == "há 12 dias"
    assert tempo.descricao_desde(HOJE - timedelta(days=1), HOJE) == "há 1 dia"
    assert tempo.descricao_desde(date(2026, 3, 30), HOJE) == "há 3 meses"
    assert tempo.descricao_desde(date(2025, 3, 30), HOJE) == "há 1 ano, 3 meses"
    assert tempo.descricao_desde(None, HOJE) is None
    assert tempo.descricao_desde(HOJE + timedelta(days=1), HOJE) is None


def test_faixa_tempo_casa_cobre_os_limites():
    def faixa(dias_ou_data):
        return tempo.faixa_tempo_casa(dias_ou_data, HOJE)

    assert faixa(HOJE) == "0-3m"
    assert faixa(date(2026, 4, 1)) == "0-3m"          # 2 meses
    assert faixa(date(2026, 3, 30)) == "3-12m"        # 3 meses cravados
    assert faixa(tempo._soma_anos(HOJE, -1)) == "1-3a"
    assert faixa(tempo._soma_anos(HOJE, -3)) == "3-5a"
    assert faixa(tempo._soma_anos(HOJE, -5)) == "5a-mais"
    assert faixa(None) is None
    assert faixa(HOJE + timedelta(days=30)) == "0-3m"  # admissão futura


def test_janela_e_label_de_mes():
    assert tempo.janela_mes(HOJE) == (date(2026, 6, 1), date(2026, 6, 30))
    assert tempo.janela_mes(date(2026, 2, 10))[1] == date(2026, 2, 28)
    assert tempo.label_mes(HOJE) == "junho/2026"
    assert tempo.desloca_mes(HOJE, -1) == date(2026, 5, 1)
    assert tempo.desloca_mes(date(2026, 12, 31), 1) == date(2027, 1, 1)


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


@pytest.fixture
def elenco(app):
    """Três colaboradores com tempos de casa bem diferentes, em 2 empresas."""
    hoje = date.today()
    acme = Empresa(nome="ACME")
    outra = Empresa(nome="Outra Ltda")
    producao = Setor(nome="Produção")
    db.session.add_all([acme, outra, producao])
    db.session.flush()
    pessoas = {
        # 100 dias de casa: último marco = 90 dias (batido), próximo = 120
        "Veterana Silva": (acme, producao, tempo._soma_anos(hoje, -6)),
        "Novato Souza": (acme, None, hoje - timedelta(days=100)),
        "Recem Lima": (outra, producao, hoje - timedelta(days=10)),
    }
    for i, (nome, (emp, setor, adm)) in enumerate(pessoas.items()):
        db.session.add(Funcionario(
            empresa_id=emp.id, setor_id=setor.id if setor else None,
            codigo=str(i), nome=nome, data_admissao=adm,
        ))
    db.session.commit()
    return {"acme": acme, "outra": outra, "producao": producao, "hoje": hoje}


def _texto(client, qs=""):
    r = client.get("/tempo-funcionarios/" + qs)
    assert r.status_code == 200
    return r.get_data(as_text=True)


def test_vista_colaborador_mostra_ultimo_marco(client_admin, elenco):
    texto = _texto(client_admin)
    assert "Último marco" in texto
    assert "90 dias" in texto          # último marco batido do Novato
    assert "há " in texto              # "há N dias/meses" ao lado
    assert "nenhum ainda" in texto     # Recem Lima, com 10 dias de casa


def test_filtro_por_empresa_e_setor(client_admin, elenco):
    texto = _texto(client_admin, f"?empresa={elenco['outra'].id}")
    assert "Recem Lima" in texto
    assert "Novato Souza" not in texto

    texto = _texto(client_admin, f"?setor={elenco['producao'].id}")
    assert "Veterana Silva" in texto
    assert "Novato Souza" not in texto


def test_filtro_por_faixa_de_tempo_de_casa(client_admin, elenco):
    texto = _texto(client_admin, "?faixa=5a-mais")
    assert "Veterana Silva" in texto
    assert "Novato Souza" not in texto
    assert "Recem Lima" not in texto

    texto = _texto(client_admin, "?faixa=0-3m")
    assert "Recem Lima" in texto
    assert "Veterana Silva" not in texto


def test_chips_de_marco_aceitam_multipla_escolha(client_admin, elenco):
    # Próximo marco: Veterana → aniversário; Novato → 120 dias; Recem → 45 dias.
    texto = _texto(client_admin, "?marco=120")
    assert "Novato Souza" in texto
    assert "Veterana Silva" not in texto

    texto = _texto(client_admin, "?marco=120&marco=aniversario")
    assert "Novato Souza" in texto
    assert "Veterana Silva" in texto
    assert "Recem Lima" not in texto


def test_seletor_de_mes_muda_o_resumo(client_admin, elenco):
    hoje = elenco["hoje"]
    texto = _texto(client_admin, f"?mes={hoje.year:04d}-{hoje.month:02d}")
    assert tempo.label_mes(hoje) in texto

    outro = tempo.desloca_mes(hoje, 5)
    texto = _texto(client_admin, f"?mes={outro.year:04d}-{outro.month:02d}")
    assert tempo.label_mes(outro) in texto
    assert "Hoje" in texto             # botão de volta ao mês corrente


def test_mes_invalido_cai_no_mes_corrente(client_admin, elenco):
    corrente = tempo.label_mes(elenco["hoje"])
    for qs in ["?mes=lixo", "?mes=2026-13", "?mes=", "?mes=2026-06-30"]:
        assert corrente in _texto(client_admin, qs), qs


def test_vista_linha_do_tempo_mostra_marco_batido(client_admin, elenco):
    hoje = elenco["hoje"]
    # Mês em que o Novato bateu os 90 dias (10 dias atrás).
    marco_90 = hoje - timedelta(days=10)
    texto = _texto(client_admin, f"?vista=linha&mes={marco_90.year:04d}-{marco_90.month:02d}")
    assert "Linha do tempo" in texto
    assert "Novato Souza" in texto
    assert "90 dias" in texto
    assert "batido há 10d" in texto


def test_navegacao_de_mes_preserva_os_filtros(client_admin, elenco):
    texto = _texto(client_admin, f"?busca=Novato&empresa={elenco['acme'].id}&marco=120")
    # As setas de mês carregam busca, empresa e chip junto.
    assert "busca=Novato" in texto
    assert f"empresa={elenco['acme'].id}" in texto
    assert "marco=120" in texto
    # E o formulário reenvia o chip/mês via hidden.
    assert '<input type="hidden" name="marco" value="120">' in texto


def test_so_com_marco_no_mes_restringe_a_tabela(client_admin, elenco):
    hoje = elenco["hoje"]
    marco_90 = hoje - timedelta(days=10)
    qs = f"?no_mes=1&mes={marco_90.year:04d}-{marco_90.month:02d}"
    texto = _texto(client_admin, qs)
    assert "Novato Souza" in texto       # bateu 90 dias nesse mês
    assert "Recem Lima" not in texto     # nenhum marco no mês
