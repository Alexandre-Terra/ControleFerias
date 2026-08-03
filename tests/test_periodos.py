"""Testes das janelas aquisitivas virtuais (funções puras, sem banco)."""
from datetime import date, timedelta
from types import SimpleNamespace

from app import periodos as pf

HOJE = date(2026, 7, 27)


def func(periodos=(), ativo=True, admissao=None, fid=1):
    return SimpleNamespace(
        id=fid, ativo=ativo, data_admissao=admissao, periodos=list(periodos)
    )


def per(inicio, fim, pid=1):
    return SimpleNamespace(id=pid, inicio=inicio, fim=fim)


# --- add_meses ---------------------------------------------------------------


def test_add_meses_clampa_no_fim_do_mes():
    assert pf.add_meses(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert pf.add_meses(date(2024, 1, 31), 1) == date(2024, 2, 29)  # bissexto
    assert pf.add_meses(date(2026, 5, 22), 12) == date(2027, 5, 22)


# --- janelas_virtuais --------------------------------------------------------


def test_janela_ancora_no_fim_do_ultimo_periodo():
    ultimo_fim = date(2026, 5, 21)
    f = func([per(date(2025, 5, 22), ultimo_fim)])
    [j] = pf.janelas_virtuais(f, HOJE)
    assert j.inicio == date(2026, 5, 22)
    assert j.fim == date(2027, 5, 21)          # início + 12 meses - 1 dia
    assert j.limite_gozo == date(2028, 5, 21)  # concessivo: fim + 12 meses
    assert j.id is None and j.virtual is True
    assert j.funcionario_id == f.id


def test_funcionario_defasado_gera_janelas_sucessivas():
    # Último período do banco fechou em 2023 → 3 janelas fechadas + 1 aberta.
    f = func([per(date(2022, 6, 1), date(2023, 5, 31))])
    janelas = pf.janelas_virtuais(f, HOJE)
    assert [j.inicio for j in janelas] == [
        date(2023, 6, 1), date(2024, 6, 1), date(2025, 6, 1), date(2026, 6, 1),
    ]
    fechadas = [j for j in janelas if j.fim <= HOJE]
    assert len(fechadas) == 3


def test_sem_periodos_usa_data_admissao():
    f = func(admissao=date(2026, 1, 15))
    [j] = pf.janelas_virtuais(f, HOJE)
    assert j.inicio == date(2026, 1, 15)  # começa NA admissão
    assert j.fim == date(2027, 1, 14)


def test_sem_periodos_e_sem_admissao_nada():
    assert pf.janelas_virtuais(func(), HOJE) == []


def test_inativo_nao_gera():
    f = func([per(date(2024, 1, 1), date(2024, 12, 31))], ativo=False)
    assert pf.janelas_virtuais(f, HOJE) == []


def test_fim_nulo_torna_ciclo_indeterminado():
    f = func([
        per(date(2024, 1, 1), date(2024, 12, 31), pid=1),
        per(date(2025, 1, 1), None, pid=2),
    ])
    assert pf.janelas_virtuais(f, HOJE) == []


def test_periodos_sobrepostos_ancoram_no_maior_fim():
    # Dados bagunçados (períodos sobrepostos): a janela nasce depois do MAIOR
    # fim e nunca repete um início já existente no banco.
    f = func([
        per(date(2025, 6, 1), date(2026, 5, 31), pid=1),
        per(date(2025, 8, 1), date(2026, 7, 1), pid=2),
    ])
    [j] = pf.janelas_virtuais(f, HOJE)
    assert j.inicio == date(2026, 7, 2)
    assert j.inicio not in {p.inicio for p in f.periodos}


def test_janela_futura_nao_nasce():
    f = func([per(date(2026, 5, 22), date(2027, 5, 21))])  # ainda aberto
    assert pf.janelas_virtuais(f, HOJE) == []


# --- periodos_efetivos -------------------------------------------------------


def test_periodos_efetivos_ordenados():
    p = per(date(2025, 5, 22), date(2026, 5, 21))
    f = func([p])
    efetivos = pf.periodos_efetivos(f, HOJE)
    assert efetivos[0] is p
    assert [x.inicio for x in efetivos] == sorted(x.inicio for x in efetivos)
    assert efetivos[1].id is None
