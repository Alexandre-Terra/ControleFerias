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

# Classes Tailwind para os badges coloridos.
BADGE = {
    VENCIDA: "bg-red-100 text-red-800 ring-1 ring-red-300",
    A_VENCER: "bg-yellow-100 text-yellow-800 ring-1 ring-yellow-300",
    TEM_DIREITO: "bg-green-100 text-green-800 ring-1 ring-green-300",
    PROGRAMADA: "bg-blue-100 text-blue-800 ring-1 ring-blue-300",
    EM_FORMACAO: "bg-gray-100 text-gray-600 ring-1 ring-gray-300",
    QUITADA: "bg-gray-50 text-gray-400 ring-1 ring-gray-200",
}


def status_periodo(periodo, hoje, dias_a_vencer, tem_programacao_ativa=False):
    """Status de um único período aquisitivo."""
    if periodo.fim is None or periodo.fim > hoje:
        return EM_FORMACAO
    restantes = periodo.dias_restantes or 0
    if restantes <= 0:
        return QUITADA
    if tem_programacao_ativa:
        return PROGRAMADA
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
