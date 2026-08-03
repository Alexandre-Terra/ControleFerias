"""Testes da lógica de status e saldo derivado (funções puras, sem banco)."""
from datetime import date, timedelta
from types import SimpleNamespace

from app import status as st

HOJE = date(2026, 7, 27)
SNAPSHOT = date(2026, 5, 27)  # data-retrato da planilha do import original
DAV = 60


def periodo(
    fim,
    saldo=None,
    limite=None,
    *,
    inicio=None,
    snapshot_em=SNAPSHOT,
    direito=None,
    pid=1,
):
    if inicio is None:
        inicio = (fim - timedelta(days=364)) if fim else HOJE - timedelta(days=100)
    return SimpleNamespace(
        id=pid,
        inicio=inicio,
        fim=fim,
        dias_direito=direito,
        saldo_snapshot=saldo,
        snapshot_em=snapshot_em,
        limite_gozo=limite,
    )


def funcionario(periodos, programacoes=(), ativo=True, data_admissao=None, fid=1):
    return SimpleNamespace(
        id=fid,
        ativo=ativo,
        data_admissao=data_admissao,
        periodos=list(periodos),
        programacoes=list(programacoes),
    )


def prog(periodo_id, dias, inicio=None, fim=None):
    return SimpleNamespace(
        periodo_aquisitivo_id=periodo_id,
        dias_gozo=dias,
        data_inicio=inicio or (HOJE + timedelta(days=40)),
        data_fim=fim,
    )


def _status(p, saldo=None, ativa=False, hoje=HOJE):
    if saldo is None:
        saldo = st.saldo_periodo(funcionario([p]), p, hoje)
    return st.status_periodo(p, hoje, DAV, saldo, tem_programacao_ativa=ativa)


# --- base_periodo: os dois regimes ------------------------------------------


def test_fechado_no_snapshot_usa_ag_importado():
    # AG de período já fechado no retrato é o saldo real (30 - gozadas pré-app).
    p = periodo(SNAPSHOT - timedelta(days=10), saldo=25)
    assert st.base_periodo(p, HOJE) == 25


def test_fronteira_fim_igual_ao_snapshot_usa_ag():
    # No dia exato do fechamento o AG proporcional já é o direito real.
    p = periodo(SNAPSHOT, saldo=12)
    assert st.base_periodo(p, HOJE) == 12


def test_aberto_no_snapshot_vale_30_ao_fechar():
    # Caso real do bug (LUIS ANTONIO RODRIGUES): AG congelado em 27,5 no
    # retrato de 27/05; o período fechou em 08/06 → direito integral de 30.
    p = periodo(
        date(2026, 6, 8),
        saldo=27.5,
        inicio=date(2025, 6, 9),
        limite=date(2027, 6, 8),
    )
    assert st.base_periodo(p, HOJE) == 30
    assert _status(p) == st.TEM_DIREITO


def test_fronteira_fim_igual_a_hoje_ja_vale_30():
    p = periodo(HOJE, saldo=27.5, inicio=HOJE - timedelta(days=364))
    assert st.base_periodo(p, HOJE) == 30


def test_em_formacao_acumula_proporcional_vivo():
    # Caso real (HIAGO LARA): AG 0,0 no retrato; aos 2 meses completos o
    # acúmulo vivo é 5,0 — e nada de QUITADA.
    p = periodo(date(2027, 5, 1), saldo=0.0, inicio=date(2026, 5, 2))
    assert st.base_periodo(p, HOJE) == 5.0
    assert _status(p) == st.EM_FORMACAO


def test_aberto_com_ag_zero_vale_30_quando_fechar():
    p = periodo(date(2027, 5, 1), saldo=0.0, inicio=date(2026, 5, 2))
    quando_fechar = date(2027, 5, 1)
    assert st.base_periodo(p, quando_fechar) == 30
    f = funcionario([p])
    saldo = st.saldo_periodo(f, p, quando_fechar)
    assert st.status_periodo(p, quando_fechar, DAV, saldo) == st.TEM_DIREITO


def test_periodo_criado_pelo_app_sem_snapshot():
    p = periodo(HOJE - timedelta(days=5), saldo=None, snapshot_em=None)
    assert st.base_periodo(p, HOJE) == 30


def test_ag_nulo_em_regime_fechado_e_quitada():
    p = periodo(SNAPSHOT - timedelta(days=10), saldo=None)
    assert st.base_periodo(p, HOJE) == 0
    assert _status(p) == st.QUITADA


# --- meses_completos ---------------------------------------------------------


def test_meses_completos_ancora_no_dia():
    ini = date(2026, 5, 2)
    assert st.meses_completos(ini, date(2026, 6, 1)) == 0
    assert st.meses_completos(ini, date(2026, 6, 2)) == 1
    assert st.meses_completos(ini, date(2026, 7, 27)) == 2


def test_meses_completos_dia_31_completa_em_fevereiro():
    ini = date(2026, 1, 31)
    assert st.meses_completos(ini, date(2026, 2, 27)) == 0
    assert st.meses_completos(ini, date(2026, 2, 28)) == 1  # clamp no fim do mês


def test_meses_completos_limites():
    assert st.meses_completos(HOJE, HOJE) == 0
    assert st.meses_completos(None, HOJE) == 0
    assert st.meses_completos(HOJE - timedelta(days=3650), HOJE) == 12  # teto


# --- saldo derivado (programações) ------------------------------------------


def test_saldo_desconta_programacoes():
    p = periodo(HOJE - timedelta(days=35), saldo=27.5, snapshot_em=HOJE - timedelta(days=60))
    f = funcionario([p], [prog(1, 10), prog(1, 5)])
    assert st.saldo_periodo(f, p, HOJE) == 15  # base 30 - 15


def test_programacao_orfa_ou_de_outro_periodo_nao_desconta():
    p = periodo(HOJE - timedelta(days=35), saldo=27.5, snapshot_em=HOJE - timedelta(days=60))
    f = funcionario([p], [prog(None, 10), prog(99, 5)])
    assert st.saldo_periodo(f, p, HOJE) == 30


def test_periodo_virtual_nao_casa_programacao():
    # id None (virtual): nem desconta, nem fica PROGRAMADA — inclusive contra
    # programação órfã (None == None não pode casar).
    p = periodo(HOJE - timedelta(days=35), snapshot_em=None, pid=None)
    f = funcionario([p], [prog(None, 10, fim=HOJE + timedelta(days=10))])
    assert st.dias_programados(f, p) == 0
    assert st.tem_programacao_ativa(f, p, HOJE) is False


def test_saldo_negativo_denuncia_inconsistencia():
    p = periodo(SNAPSHOT - timedelta(days=10), saldo=5)
    f = funcionario([p], [prog(1, 10)])
    assert st.saldo_periodo(f, p, HOJE) == -5  # sem clamp, de propósito


# --- direito_periodo ---------------------------------------------------------


def test_direito_fechado_no_snapshot_e_o_importado():
    p = periodo(SNAPSHOT - timedelta(days=10), saldo=10, direito=28)
    assert st.direito_periodo(p, HOJE) == 28  # pode ser < 30 (faltas)


def test_direito_derivado_e_a_base():
    fechado = periodo(date(2026, 6, 8), saldo=27.5, inicio=date(2025, 6, 9))
    aberto = periodo(date(2027, 5, 1), saldo=0.0, inicio=date(2026, 5, 2))
    assert st.direito_periodo(fechado, HOJE) == 30
    assert st.direito_periodo(aberto, HOJE) == 5.0


# --- status_periodo ----------------------------------------------------------


def test_em_formacao_quando_aquisitivo_aberto():
    p = periodo(HOJE + timedelta(days=10))
    assert _status(p) == st.EM_FORMACAO


def test_quitada_quando_saldo_derivado_zera():
    p = periodo(HOJE - timedelta(days=100), saldo=30, limite=HOJE + timedelta(days=100),
                snapshot_em=HOJE)
    f = funcionario([p], [prog(1, 30, inicio=HOJE - timedelta(days=60),
                               fim=HOJE - timedelta(days=31))])  # já gozada
    saldo = st.saldo_periodo(f, p, HOJE)
    ativa = st.tem_programacao_ativa(f, p, HOJE)
    assert ativa is False
    assert st.status_periodo(p, HOJE, DAV, saldo, ativa) == st.QUITADA


def test_vencida_passou_do_limite():
    p = periodo(HOJE - timedelta(days=400), saldo=15, limite=HOJE - timedelta(days=1))
    assert _status(p) == st.VENCIDA


def test_fronteira_limite_igual_a_hoje_e_a_vencer():
    p = periodo(HOJE - timedelta(days=400), saldo=15, limite=HOJE)
    assert _status(p) == st.A_VENCER


def test_a_vencer_dentro_do_limiar():
    p = periodo(HOJE - timedelta(days=300), saldo=30, limite=HOJE + timedelta(days=40))
    assert _status(p) == st.A_VENCER


def test_tem_direito():
    p = periodo(HOJE - timedelta(days=30), saldo=30, limite=HOJE + timedelta(days=200))
    assert _status(p) == st.TEM_DIREITO


def test_programada_quando_ha_programacao_ativa():
    p = periodo(HOJE - timedelta(days=30), saldo=30, limite=HOJE + timedelta(days=200))
    assert _status(p, ativa=True) == st.PROGRAMADA


# --- agregação ---------------------------------------------------------------


def test_agregado_pior_status_vence():
    assert st.status_agregado([st.EM_FORMACAO, st.VENCIDA]) == st.VENCIDA
    assert st.status_agregado([st.QUITADA, st.TEM_DIREITO]) == st.TEM_DIREITO


def test_tem_direito_funcionario():
    p_aberto = periodo(HOJE + timedelta(days=10), pid=2)
    p_direito = periodo(
        SNAPSHOT - timedelta(days=30), saldo=8, limite=HOJE + timedelta(days=200), pid=1
    )
    f = funcionario([p_direito, p_aberto])
    assert st.tem_direito(f, HOJE, DAV) is True
    assert st.status_funcionario(f, HOJE, DAV) == st.TEM_DIREITO


def test_programacao_ativa_muda_status_agregado():
    p = periodo(HOJE - timedelta(days=30), saldo=30, limite=HOJE + timedelta(days=200))
    f = funcionario(
        [p],
        [prog(1, 10, inicio=HOJE + timedelta(days=40), fim=HOJE + timedelta(days=49))],
    )
    assert st.status_funcionario(f, HOJE, DAV) == st.PROGRAMADA


def test_periodos_com_status_devolve_triplas_com_janela_virtual():
    p = periodo(date(2026, 6, 8), saldo=27.5, inicio=date(2025, 6, 9),
                limite=date(2027, 6, 8))
    f = funcionario([p], [prog(1, 10, fim=HOJE - timedelta(days=1))])
    triplas = st.periodos_com_status(f, HOJE, DAV)

    # O período do banco vem com saldo derivado…
    (per, s, saldo) = triplas[0]
    assert per is p
    assert s == st.TEM_DIREITO
    assert saldo == 20  # 30 - 10 já gozados

    # …e a janela aquisitiva seguinte (virtual) já aparece em formação.
    (per2, s2, saldo2) = triplas[1]
    assert per2.id is None
    assert per2.inicio == date(2026, 6, 9)
    assert s2 == st.EM_FORMACAO
    assert saldo2 == 2.5  # 1 mês completo desde 09/06
