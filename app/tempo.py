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
"""
import calendar
from datetime import timedelta

# (dias_de_casa, dias_de_antecedencia_do_aviso)
MARCOS_DIAS = [(45, 5), (90, 5), (120, 0)]
ANTECEDENCIA_ANIVERSARIO = 2


def _soma_anos(d, anos):
    """``d`` + ``anos`` anos; 29/02 vira 28/02 em ano não bissexto."""
    try:
        return d.replace(year=d.year + anos)
    except ValueError:
        return d.replace(year=d.year + anos, day=28)


def _label_aniversario(anos):
    return "1 ano" if anos == 1 else f"{anos} anos"


def _marco(tipo, label, data_marco, antecedencia, hoje):
    data_aviso = data_marco - timedelta(days=antecedencia)
    return {
        "tipo": tipo,                       # "dias" | "aniversario"
        "label": label,                     # "45 dias", "1 ano", "3 anos", …
        "data": data_marco,                 # data em que o marco é atingido
        "antecedencia": antecedencia,       # dias de antecedência do aviso
        "data_aviso": data_aviso,           # dia em que o alerta deve disparar
        "dias_faltam": (data_marco - hoje).days,
        "alertar_hoje": data_aviso == hoje,
    }


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
    marcos = []
    for dias, antec in MARCOS_DIAS:
        data_marco = data_admissao + timedelta(days=dias)
        if data_marco >= hoje:
            marcos.append(_marco("dias", f"{dias} dias", data_marco, antec, hoje))
    n = _proximo_aniversario_n(data_admissao, hoje)
    data_aniv = _soma_anos(data_admissao, n)
    marcos.append(
        _marco(
            "aniversario",
            _label_aniversario(n),
            data_aniv,
            ANTECEDENCIA_ANIVERSARIO,
            hoje,
        )
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


def descricao_tempo_casa(data_admissao, hoje):
    """Tempo de casa legível: "2 anos, 3 meses" / "18 dias" / "—"."""
    if data_admissao is None:
        return "—"
    if data_admissao > hoje:
        return "ainda não iniciou"
    anos, meses, dias = _ymd(data_admissao, hoje)
    partes = []
    if anos:
        partes.append(f"{anos} ano" + ("s" if anos != 1 else ""))
    if meses:
        partes.append(f"{meses} {'mês' if meses == 1 else 'meses'}")
    if not anos and not meses and dias:
        partes.append(f"{dias} dia" + ("s" if dias != 1 else ""))
    return ", ".join(partes) or "admitido hoje"
