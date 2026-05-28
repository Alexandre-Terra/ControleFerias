"""Testes da lógica de status (funções puras, sem banco)."""
from datetime import date, timedelta
from types import SimpleNamespace

from app import status as st

HOJE = date(2026, 5, 27)
DAV = 60


def periodo(fim, restantes, limite, pid=1):
    return SimpleNamespace(
        id=pid, fim=fim, dias_restantes=restantes, limite_gozo=limite
    )


def test_em_formacao_quando_aquisitivo_aberto():
    # fim no futuro -> ainda adquirindo, NÃO é "tem direito"
    p = periodo(HOJE + timedelta(days=10), 22.5, None)
    assert st.status_periodo(p, HOJE, DAV) == st.EM_FORMACAO


def test_tem_direito():
    p = periodo(HOJE - timedelta(days=30), 30, HOJE + timedelta(days=200))
    assert st.status_periodo(p, HOJE, DAV) == st.TEM_DIREITO


def test_a_vencer_dentro_do_limiar():
    p = periodo(HOJE - timedelta(days=300), 30, HOJE + timedelta(days=40))
    assert st.status_periodo(p, HOJE, DAV) == st.A_VENCER


def test_vencida_passou_do_limite():
    p = periodo(HOJE - timedelta(days=400), 15, HOJE - timedelta(days=1))
    assert st.status_periodo(p, HOJE, DAV) == st.VENCIDA


def test_quitada_sem_saldo():
    p = periodo(HOJE - timedelta(days=100), 0, HOJE + timedelta(days=100))
    assert st.status_periodo(p, HOJE, DAV) == st.QUITADA


def test_programada_quando_ha_programacao_ativa():
    p = periodo(HOJE - timedelta(days=30), 30, HOJE + timedelta(days=200))
    assert st.status_periodo(p, HOJE, DAV, tem_programacao_ativa=True) == st.PROGRAMADA


def test_agregado_pior_status_vence():
    # VENCIDA + EM_FORMACAO -> funcionário = VENCIDA
    assert st.status_agregado([st.EM_FORMACAO, st.VENCIDA]) == st.VENCIDA
    assert st.status_agregado([st.QUITADA, st.TEM_DIREITO]) == st.TEM_DIREITO


def test_tem_direito_funcionario():
    p_aberto = periodo(HOJE + timedelta(days=10), 22.5, None, pid=2)
    p_direito = periodo(HOJE - timedelta(days=30), 8, HOJE + timedelta(days=200), pid=1)
    f = SimpleNamespace(periodos=[p_direito, p_aberto], programacoes=[])
    assert st.tem_direito(f, HOJE, DAV) is True
    assert st.status_funcionario(f, HOJE, DAV) == st.TEM_DIREITO


def test_programacao_ativa_muda_status_agregado():
    p = periodo(HOJE - timedelta(days=30), 30, HOJE + timedelta(days=200), pid=1)
    prog = SimpleNamespace(
        periodo_aquisitivo_id=1,
        data_inicio=HOJE + timedelta(days=40),
        data_fim=HOJE + timedelta(days=70),
    )
    f = SimpleNamespace(periodos=[p], programacoes=[prog])
    assert st.status_funcionario(f, HOJE, DAV) == st.PROGRAMADA
