"""Lógica de status de férias (CLT) — funções puras, sem acesso a banco.

O status é sempre derivado da data de hoje; nunca é armazenado.
Regra-chave: "tem direito" exige período aquisitivo fechado (fim <= hoje)
E dias restantes > 0.
"""

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


def status_periodo(periodo, hoje, dias_a_vencer, tem_programacao_ativa=False):
    """Status de um único período aquisitivo."""
    if periodo.fim is None or periodo.fim > hoje:
        return EM_FORMACAO
    if tem_programacao_ativa:
        return PROGRAMADA
    restantes = periodo.dias_restantes or 0
    if restantes <= 0:
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
    for prog in funcionario.programacoes:
        if prog.periodo_aquisitivo_id == periodo.id:
            fim = prog.data_fim or prog.data_inicio
            if fim and fim >= hoje:
                return True
    return False


def periodos_com_status(funcionario, hoje, dias_a_vencer):
    """Lista de (periodo, status) para cada período do funcionário."""
    resultado = []
    for periodo in funcionario.periodos:
        ativa = tem_programacao_ativa(funcionario, periodo, hoje)
        resultado.append((periodo, status_periodo(periodo, hoje, dias_a_vencer, ativa)))
    return resultado


def status_funcionario(funcionario, hoje, dias_a_vencer):
    """Status agregado (badge) do funcionário."""
    statuses = [s for _, s in periodos_com_status(funcionario, hoje, dias_a_vencer)]
    return status_agregado(statuses)


def tem_direito(funcionario, hoje, dias_a_vencer):
    """Resposta direta à pergunta dos gestores: já tem direito a férias?

    Verdadeiro se existe período com direito adquirido e saldo, ainda não
    totalmente programado/gozado (TEM_DIREITO, A_VENCER ou VENCIDA).
    """
    statuses = [s for _, s in periodos_com_status(funcionario, hoje, dias_a_vencer)]
    return any(s in (TEM_DIREITO, A_VENCER, VENCIDA) for s in statuses)
