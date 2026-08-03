"""Marcos de tempo de serviço (a partir da data de admissão) — funções puras.

Como em ``app/status.py``, nada é persistido: os marcos são derivados de
``hoje`` e da ``data_admissao``. Usado pela página admin "Tempo Funcionários" e
pelo digest do WhatsApp (Z-API).

Dois tipos de marco:

- **Por dias corridos de casa** (45, 90, 120) — janelas do contrato de
  experiência e estabilidade. Cada um avisa com uma antecedência fixa:
  45 e 90 dias avisam **5 dias antes**; 120 dias avisa **no mesmo dia**.
- **Aniversários anuais** (1 ano, 2 anos, …) — avisam **2 dias antes**, tanto o
  primeiro ano quanto, sucessivamente, todos os seguintes.

O "dia de aviso" de um marco é ``data_marco - antecedencia``. Um marco
"alerta hoje" quando esse dia de aviso é exatamente ``hoje`` — é nesse dia que
ele entra no resumo do WhatsApp (envio único, fiel a "avisar com N dias de
antecedência"). A página admin mostra sempre o próximo marco de cada um, então
a visibilidade não depende do disparo do dia.

Os marcos existem nos dois sentidos do tempo: ``marcos_proximos`` olha para a
frente (é o que alimenta o WhatsApp), ``ultimo_marco`` olha para trás e
``marcos_no_intervalo`` varre uma janela qualquer — é o que a página usa para
responder "quantos bateram ou baterão marco neste mês".
"""
import calendar
from datetime import timedelta

from .periodos import add_meses

# (dias_de_casa, dias_de_antecedencia_do_aviso)
MARCOS_DIAS = [(45, 5), (90, 5), (120, 0)]
ANTECEDENCIA_ANIVERSARIO = 2

# Chave estável de cada tipo de marco (valor na URL, agrupamento no resumo).
CHAVE_ANIVERSARIO = "aniversario"
CHAVES_MARCO = [str(dias) for dias, _ in MARCOS_DIAS] + [CHAVE_ANIVERSARIO]

# Faixas de tempo de casa: (slug, rótulo, meses_min, meses_max_exclusivo).
# Slugs sem "+": em query string um "+" cru vira espaço.
FAIXAS_TEMPO = [
    ("0-3m", "Até 3 meses", 0, 3),
    ("3-12m", "3 a 12 meses", 3, 12),
    ("1-3a", "1 a 3 anos", 12, 36),
    ("3-5a", "3 a 5 anos", 36, 60),
    ("5a-mais", "5 anos ou mais", 60, None),
]

MESES_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def _soma_anos(d, anos):
    """``d`` + ``anos`` anos; 29/02 vira 28/02 em ano não bissexto."""
    try:
        return d.replace(year=d.year + anos)
    except ValueError:
        return d.replace(year=d.year + anos, day=28)


def _label_aniversario(anos):
    return "1 ano" if anos == 1 else f"{anos} anos"


def _marco(tipo, chave, label, data_marco, antecedencia, hoje):
    data_aviso = data_marco - timedelta(days=antecedencia)
    return {
        "tipo": tipo,                       # "dias" | "aniversario"
        "chave": chave,                     # "45" | "90" | "120" | "aniversario"
        "label": label,                     # "45 dias", "1 ano", "3 anos", …
        "data": data_marco,                 # data em que o marco é atingido
        "antecedencia": antecedencia,       # dias de antecedência do aviso
        "data_aviso": data_aviso,           # dia em que o alerta deve disparar
        "dias_faltam": (data_marco - hoje).days,   # negativo se já passou
        "batido": data_marco <= hoje,       # o dia do marco conta como batido
        "alertar_hoje": data_aviso == hoje,
    }


def _marco_dias(dias, antecedencia, data_admissao, hoje):
    data_marco = data_admissao + timedelta(days=dias)
    return _marco("dias", str(dias), f"{dias} dias", data_marco, antecedencia, hoje)


def _marco_aniversario(n, data_admissao, hoje):
    return _marco(
        "aniversario",
        CHAVE_ANIVERSARIO,
        _label_aniversario(n),
        _soma_anos(data_admissao, n),
        ANTECEDENCIA_ANIVERSARIO,
        hoje,
    )


def _proximo_aniversario_n(data_admissao, hoje):
    """Menor ``n >= 1`` cujo aniversário cai em ``hoje`` ou no futuro."""
    n = max(1, hoje.year - data_admissao.year)
    while _soma_anos(data_admissao, n) < hoje:
        n += 1
    return n


def marcos_proximos(data_admissao, hoje):
    """Marcos ainda por vir (``data >= hoje``), ordenados por data.

    Inclui os marcos por dias (45/90/120) que ainda não passaram e o próximo
    aniversário. Lista vazia se ``data_admissao`` for ``None``.

    Basta o próximo aniversário: como ``data_aviso = aniversário - 2``, só o
    aniversário em ``(hoje, hoje + 1 ano]`` pode ter dia de aviso hoje (quando
    cai em ``hoje + 2``); os anteriores já avisaram.
    """
    if data_admissao is None:
        return []
    marcos = [
        _marco_dias(dias, antec, data_admissao, hoje)
        for dias, antec in MARCOS_DIAS
        if data_admissao + timedelta(days=dias) >= hoje
    ]
    marcos.append(
        _marco_aniversario(_proximo_aniversario_n(data_admissao, hoje), data_admissao, hoje)
    )
    marcos.sort(key=lambda mk: mk["data"])
    return marcos


def proximo_marco(data_admissao, hoje):
    """O marco mais próximo (menor data) ou ``None``."""
    marcos = marcos_proximos(data_admissao, hoje)
    return marcos[0] if marcos else None


def alertas_do_dia(data_admissao, hoje):
    """Marcos cujo dia de aviso é exatamente ``hoje`` (entram no WhatsApp)."""
    return [mk for mk in marcos_proximos(data_admissao, hoje) if mk["alertar_hoje"]]


def _ultimo_aniversario_n(data_admissao, hoje):
    """Maior ``n >= 1`` cujo aniversário já caiu (``<= hoje``); 0 se nenhum.

    Decrementa a partir da diferença de anos do calendário em vez de usar
    ``_ymd``: para admissão em 29/02, o marco de 1 ano cai em 28/02 do ano
    seguinte (ver ``_soma_anos``), dia em que ``_ymd`` ainda diria "0 anos".
    """
    n = hoje.year - data_admissao.year
    while n >= 1 and _soma_anos(data_admissao, n) > hoje:
        n -= 1
    return max(0, n)


def ultimo_marco(data_admissao, hoje):
    """Marco mais recente já atingido (``data <= hoje``) ou ``None``.

    ``None`` para quem ainda não completou 45 dias de casa — e para admissão
    futura ou ausente.
    """
    if data_admissao is None or data_admissao > hoje:
        return None
    marcos = [
        _marco_dias(dias, antec, data_admissao, hoje)
        for dias, antec in MARCOS_DIAS
        if data_admissao + timedelta(days=dias) <= hoje
    ]
    n = _ultimo_aniversario_n(data_admissao, hoje)
    if n:
        marcos.append(_marco_aniversario(n, data_admissao, hoje))
    return max(marcos, key=lambda mk: mk["data"]) if marcos else None


def marcos_no_intervalo(data_admissao, inicio, fim, hoje):
    """Todos os marcos com data em ``[inicio, fim]``, ordenados por data.

    Diferente de ``marcos_proximos``, varre a janela nos dois sentidos: serve
    para contar quem **bateu** e quem **vai bater** marco num mês. Inclui todos
    os aniversários da janela (não só o próximo).
    """
    if data_admissao is None:
        return []
    marcos = [
        _marco_dias(dias, antec, data_admissao, hoje)
        for dias, antec in MARCOS_DIAS
        if inicio <= data_admissao + timedelta(days=dias) <= fim
    ]
    n = max(1, inicio.year - data_admissao.year - 1)
    while _soma_anos(data_admissao, n) <= fim:
        if _soma_anos(data_admissao, n) >= inicio:
            marcos.append(_marco_aniversario(n, data_admissao, hoje))
        n += 1
    marcos.sort(key=lambda mk: mk["data"])
    return marcos


def resumo_marcos(marcos):
    """Contagens de uma lista de marcos: total, batidos, a bater e por chave."""
    resumo = {
        "total": len(marcos),
        "batidos": sum(1 for mk in marcos if mk["batido"]),
        "por_chave": {c: {"total": 0, "batidos": 0, "a_bater": 0} for c in CHAVES_MARCO},
    }
    resumo["a_bater"] = resumo["total"] - resumo["batidos"]
    for mk in marcos:
        alvo = resumo["por_chave"][mk["chave"]]
        alvo["total"] += 1
        alvo["batidos" if mk["batido"] else "a_bater"] += 1
    return resumo


def tempo_de_casa_dias(data_admissao, hoje):
    """Dias corridos desde a admissão (``None`` se sem data; negativo se futura)."""
    if data_admissao is None:
        return None
    return (hoje - data_admissao).days


def _ymd(inicio, fim):
    """Diferença de calendário entre ``inicio <= fim`` em (anos, meses, dias)."""
    anos = fim.year - inicio.year
    meses = fim.month - inicio.month
    dias = fim.day - inicio.day
    if dias < 0:
        mes_ant = fim.month - 1 or 12
        ano_ant = fim.year if fim.month > 1 else fim.year - 1
        dias += calendar.monthrange(ano_ant, mes_ant)[1]
        meses -= 1
    if meses < 0:
        meses += 12
        anos -= 1
    return anos, meses, dias


def _texto_ymd(anos, meses, dias):
    """"2 anos, 3 meses" / "18 dias" / "" (quando é o mesmo dia).

    Dias só aparecem quando não há anos nem meses — "1 ano, 3 meses e 4 dias"
    é ruído para quem só quer situar o marco no tempo.
    """
    partes = []
    if anos:
        partes.append(f"{anos} ano" + ("s" if anos != 1 else ""))
    if meses:
        partes.append(f"{meses} {'mês' if meses == 1 else 'meses'}")
    if not anos and not meses and dias:
        partes.append(f"{dias} dia" + ("s" if dias != 1 else ""))
    return ", ".join(partes)


def descricao_tempo_casa(data_admissao, hoje):
    """Tempo de casa legível: "2 anos, 3 meses" / "18 dias" / "—"."""
    if data_admissao is None:
        return "—"
    if data_admissao > hoje:
        return "ainda não iniciou"
    return _texto_ymd(*_ymd(data_admissao, hoje)) or "admitido hoje"


def descricao_desde(data, hoje):
    """Há quanto tempo ``data`` ficou para trás: "hoje" / "há 12 dias" / "há 2 anos".

    ``None`` se ``data`` for nula ou ainda estiver no futuro (aí quem responde
    é ``dias_faltam`` do marco).
    """
    if data is None or data > hoje:
        return None
    return f"há {_texto_ymd(*_ymd(data, hoje))}" if data < hoje else "hoje"


def meses_de_casa(data_admissao, hoje):
    """Meses completos desde a admissão (``None`` sem data; 0 se futura)."""
    if data_admissao is None:
        return None
    if data_admissao > hoje:
        return 0
    anos, meses, _ = _ymd(data_admissao, hoje)
    return anos * 12 + meses


def faixa_tempo_casa(data_admissao, hoje):
    """Slug da faixa de tempo de casa (ver ``FAIXAS_TEMPO``) ou ``None``."""
    meses = meses_de_casa(data_admissao, hoje)
    if meses is None:
        return None
    for slug, _rotulo, minimo, maximo in FAIXAS_TEMPO:
        if meses >= minimo and (maximo is None or meses < maximo):
            return slug
    return None


def janela_mes(ref):
    """(primeiro, último) dia do mês em que ``ref`` cai."""
    primeiro = ref.replace(day=1)
    ultimo = primeiro.replace(day=calendar.monthrange(ref.year, ref.month)[1])
    return primeiro, ultimo


def desloca_mes(ref, n):
    """Primeiro dia do mês ``n`` meses adiante (ou atrás, se negativo)."""
    return add_meses(ref.replace(day=1), n)


def label_mes(ref):
    """"agosto/2026" — nome do mês em pt-BR (``strftime`` depende do locale)."""
    return f"{MESES_PT[ref.month - 1]}/{ref.year}"
