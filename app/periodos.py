"""Ciclo de períodos aquisitivos: janelas virtuais derivadas — puro, sem banco.

O banco guarda só os períodos conhecidos (import + materializados ao programar).
As janelas seguintes são DERIVADAS de hoje: sucessivas, de 12 meses, a partir do
fim do último período conhecido (ou da admissão, para quem não tem nenhum).
Nada de cron: o período novo "aparece" sozinho quando o tempo passa e só vira
linha no banco quando alguém programa férias contra ele (routes/programacao).
"""
import calendar
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class PeriodoVirtual:
    """Janela aquisitiva ainda sem linha no banco (``id is None`` = virtual).

    Espelha os atributos de ``PeriodoAquisitivo`` que ``status.py`` consome.
    """

    funcionario_id: int
    inicio: date
    fim: date
    limite_gozo: date
    id: None = None
    snapshot_em: None = None
    saldo_snapshot: None = None
    dias_direito: None = None
    dias_abono: None = None
    decimo_terceiro: None = None
    virtual: bool = True


def add_meses(d, n):
    """Data ``d`` + ``n`` meses, dia clampado ao último dia do mês destino."""
    idx = d.year * 12 + (d.month - 1) + n
    ano, mes = idx // 12, idx % 12 + 1
    return date(ano, mes, min(d.day, calendar.monthrange(ano, mes)[1]))


def janelas_virtuais(funcionario, hoje):
    """Janelas de 12 meses após o último período, enquanto ``inicio <= hoje``.

    Regras:
    - funcionário inativo não acumula janela nova;
    - âncora = maior ``fim`` dos períodos do banco; sem período nenhum, a
      primeira janela começa NA data de admissão; sem admissão, nada;
    - período com ``fim`` nulo torna o ciclo indeterminado → nada;
    - lacunas históricas entre períodos do banco não são preenchidas — a
      planilha é autoritativa para o passado (pode haver suspensão de contrato);
    - ``limite_gozo`` = fim do concessivo (art. 134: 12 meses após fechar).
    """
    if not funcionario.ativo:
        return []
    periodos = list(funcionario.periodos)
    if any(p.fim is None for p in periodos):
        return []
    if periodos:
        proximo_inicio = max(p.fim for p in periodos) + timedelta(days=1)
    elif funcionario.data_admissao:
        proximo_inicio = funcionario.data_admissao
    else:
        return []

    inicios_existentes = {p.inicio for p in periodos}
    janelas = []
    while proximo_inicio <= hoje:
        fim = add_meses(proximo_inicio, 12) - timedelta(days=1)
        if proximo_inicio not in inicios_existentes:
            # (a unique funcionario_id+inicio do banco é a rede de verdade)
            janelas.append(
                PeriodoVirtual(
                    funcionario_id=funcionario.id,
                    inicio=proximo_inicio,
                    fim=fim,
                    limite_gozo=add_meses(fim, 12),
                )
            )
        proximo_inicio = fim + timedelta(days=1)
    return janelas


def periodos_efetivos(funcionario, hoje):
    """Períodos do banco + janelas virtuais, ordenados por início."""
    todos = list(funcionario.periodos) + janelas_virtuais(funcionario, hoje)
    todos.sort(key=lambda p: p.inicio)
    return todos
