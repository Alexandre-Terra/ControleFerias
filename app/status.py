"""Lógica de status e saldo de férias (CLT) — funções puras, sem acesso a banco.

Status e saldo são sempre derivados da data de hoje; nunca são armazenados.
Regra-chave: "tem direito" exige período aquisitivo fechado (fim <= hoje)
E saldo derivado > 0.

O saldo atual de um período é ``base_periodo - dias_programados``:

- **base**: o que o período confere hoje. Período que já estava fechado na
  data-retrato do import (``snapshot_em``) usa o AG da planilha como está —
  ele embute férias gozadas antes do app existir. Qualquer outro período
  (aberto no retrato, ou criado pelo app) rende o direito integral de 30 dias
  ao fechar (art. 130, caput — faltas fora de escopo) e, enquanto em formação,
  o acúmulo proporcional de 1/12 dos 30 por mês completado (2,5/mês, a mesma
  convenção da planilha). É isso que faz o saldo "virar 30" sozinho quando o
  período completa 12 meses — a coluna ``saldo_snapshot`` nunca é mutada.
- **programações** registradas no app consomem o saldo enquanto a linha
  existir; cancelar apaga a linha e o saldo volta sem contabilidade extra.
"""
import calendar

from . import periodos as pf

# Status possíveis, em ordem de PRECEDÊNCIA (pior caso primeiro).
VENCIDA = "VENCIDA"
A_VENCER = "A_VENCER"
TEM_DIREITO = "TEM_DIREITO"
PROGRAMADA = "PROGRAMADA"
EM_FORMACAO = "EM_FORMACAO"
QUITADA = "QUITADA"

PRECEDENCIA = [VENCIDA, A_VENCER, TEM_DIREITO, PROGRAMADA, EM_FORMACAO, QUITADA]

LABELS = {
    VENCIDA: "Vencida",
    A_VENCER: "A vencer",
    TEM_DIREITO: "Tem direito",
    PROGRAMADA: "Programada",
    EM_FORMACAO: "Em formação",
    QUITADA: "Quitada",
}

# Classe de status do design "Editorial Risk" — define a CSS var --c usada por
# pills, dots, faixas e realces. Ver app/static/css/app.css (.s-risk, .s-warn, …).
CLASS = {
    VENCIDA: "s-risk",
    A_VENCER: "s-warn",
    TEM_DIREITO: "s-ok",
    PROGRAMADA: "s-info",
    EM_FORMACAO: "s-idle",
    QUITADA: "s-done",
}

# Nome curto da CSS var de cor (var(--risk), var(--warn), …) para os gráficos.
VAR = {
    VENCIDA: "risk",
    A_VENCER: "warn",
    TEM_DIREITO: "ok",
    PROGRAMADA: "info",
    EM_FORMACAO: "idle",
    QUITADA: "done",
}

# Direito integral por período aquisitivo e acúmulo por mês completado.
DIAS_INTEGRAIS = 30.0
DIAS_POR_MES = 2.5


def meses_completos(inicio, hoje):
    """Meses completos entre ``inicio`` e ``hoje`` (0..12), âncora no dia do início.

    O dia-âncora é clampado ao último dia do mês corrente — início dia 31
    completa o mês em 28/29 de fevereiro, como no calendário civil.
    """
    if inicio is None or hoje <= inicio:
        return 0
    meses = (hoje.year - inicio.year) * 12 + (hoje.month - inicio.month)
    ancora = min(inicio.day, calendar.monthrange(hoje.year, hoje.month)[1])
    if hoje.day < ancora:
        meses -= 1
    return max(0, min(12, meses))


def fechado_no_snapshot(periodo):
    """True se o período já estava fechado na data-retrato do import."""
    return (
        periodo.snapshot_em is not None
        and periodo.fim is not None
        and periodo.fim <= periodo.snapshot_em
    )


def base_periodo(periodo, hoje):
    """Dias que o período confere hoje, antes de descontar programações."""
    if fechado_no_snapshot(periodo):
        return periodo.saldo_snapshot or 0.0
    if periodo.fim is not None and periodo.fim <= hoje:
        return DIAS_INTEGRAIS
    return min(DIAS_INTEGRAIS, DIAS_POR_MES * meses_completos(periodo.inicio, hoje))


def dias_programados(funcionario, periodo):
    """Soma de dias_gozo das programações ligadas ao período.

    Período virtual (``id is None``) não pode ter programação — programar
    contra ele o materializa antes (ver routes/programacao). A guarda também
    impede programação órfã (FK nula) de casar com virtual via ``None == None``.
    """
    if periodo.id is None:
        return 0
    return sum(
        prog.dias_gozo or 0
        for prog in funcionario.programacoes
        if prog.periodo_aquisitivo_id == periodo.id
    )


def saldo_periodo(funcionario, periodo, hoje):
    """Saldo atual do período: base menos o programado no app.

    Sem clamp em zero de propósito — saldo negativo denuncia inconsistência de
    dados (ex.: re-import de planilha que já descontava férias registradas no
    app) em vez de escondê-la.
    """
    return base_periodo(periodo, hoje) - dias_programados(funcionario, periodo)


def direito_periodo(periodo, hoje):
    """Dias de direito do período (coluna "Direito" do detalhe).

    Fechado na data-retrato: o AC importado (pode ser < 30 por faltas
    registradas na planilha). Demais: a própria base — 30 ao fechar, acúmulo
    proporcional vivo em formação.
    """
    if fechado_no_snapshot(periodo):
        return periodo.dias_direito
    return base_periodo(periodo, hoje)


def status_periodo(periodo, hoje, dias_a_vencer, saldo, tem_programacao_ativa=False):
    """Status de um único período aquisitivo.

    ``saldo`` é o saldo derivado (``saldo_periodo``) — parâmetro obrigatório
    para nenhum chamador cair por engano no valor congelado da coluna.
    """
    if periodo.fim is None or periodo.fim > hoje:
        return EM_FORMACAO
    if tem_programacao_ativa:
        return PROGRAMADA
    if saldo <= 0:
        return QUITADA
    if periodo.limite_gozo and periodo.limite_gozo < hoje:
        return VENCIDA
    if periodo.limite_gozo and (periodo.limite_gozo - hoje).days <= dias_a_vencer:
        return A_VENCER
    return TEM_DIREITO


def status_agregado(status_list):
    """Pior status entre os períodos de um funcionário."""
    for s in PRECEDENCIA:
        if s in status_list:
            return s
    return EM_FORMACAO


def tem_programacao_ativa(funcionario, periodo, hoje):
    """True se há programação (futura ou em curso) ligada a este período."""
    if periodo.id is None:
        return False
    for prog in funcionario.programacoes:
        if prog.periodo_aquisitivo_id == periodo.id:
            fim = prog.data_fim or prog.data_inicio
            if fim and fim >= hoje:
                return True
    return False


def periodos_com_status(funcionario, hoje, dias_a_vencer):
    """Lista de (periodo, status, saldo) por período — banco E janelas virtuais.

    É o ponto único por onde listas, painel, detalhe e digest enxergam os
    períodos; as janelas ainda sem linha no banco entram aqui de graça.
    """
    resultado = []
    for periodo in pf.periodos_efetivos(funcionario, hoje):
        ativa = tem_programacao_ativa(funcionario, periodo, hoje)
        saldo = saldo_periodo(funcionario, periodo, hoje)
        resultado.append(
            (periodo, status_periodo(periodo, hoje, dias_a_vencer, saldo, ativa), saldo)
        )
    return resultado


def status_funcionario(funcionario, hoje, dias_a_vencer):
    """Status agregado (badge) do funcionário."""
    statuses = [s for _, s, _ in periodos_com_status(funcionario, hoje, dias_a_vencer)]
    return status_agregado(statuses)


def tem_direito(funcionario, hoje, dias_a_vencer):
    """Resposta direta à pergunta dos gestores: já tem direito a férias?

    Verdadeiro se existe período com direito adquirido e saldo, ainda não
    totalmente programado/gozado (TEM_DIREITO, A_VENCER ou VENCIDA).
    """
    statuses = [s for _, s, _ in periodos_com_status(funcionario, hoje, dias_a_vencer)]
    return any(s in (TEM_DIREITO, A_VENCER, VENCIDA) for s in statuses)
