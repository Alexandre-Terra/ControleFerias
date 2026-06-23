"""Montagem do resumo de férias enviado por WhatsApp (Z-API).

Puro do ponto de vista de escrita: só lê funcionários/períodos e deriva o status
via ``app/status.py`` (nunca persiste status). A renderização dos modelos é
**segura**: variáveis ``{chave}`` desconhecidas (ou ``{`` soltos) ficam intactas,
sem quebrar como faria ``str.format``.
"""
import re
from datetime import date

from sqlalchemy.orm import selectinload

from . import status
from .models import Funcionario

# Teto de linhas no resumo — WhatsApp/Z-API truncam mensagens muito longas
# (~4096 chars). O excedente vira um rodapé "…e mais N".
MAX_LINHAS = 40

_VAR_RE = re.compile(r"\{(\w+)\}")


def _render(template, valores):
    """Substitui ``{chave}`` pelos valores; deixa chaves desconhecidas intactas."""
    def repl(m):
        chave = m.group(1)
        if chave in valores:
            return str(valores[chave])
        return m.group(0)

    return _VAR_RE.sub(repl, template or "")


def _fmt_dias(valor):
    if valor is None:
        return "—"
    return f"{int(valor)}" if float(valor).is_integer() else f"{valor}"


def _status_habilitados(config):
    habilitados = set()
    if config.notificar_vencida:
        habilitados.add(status.VENCIDA)
    if config.notificar_a_vencer:
        habilitados.add(status.A_VENCER)
    if config.notificar_tem_direito:
        habilitados.add(status.TEM_DIREITO)
    return habilitados


def _periodo_representativo(funcionario, hoje, dias_a_vencer):
    """Status agregado + o período mais urgente que o justifica (menor limite)."""
    pares = status.periodos_com_status(funcionario, hoje, dias_a_vencer)
    agregado = status.status_agregado([s for _, s in pares])
    candidatos = [p for p, s in pares if s == agregado]
    periodo = None
    if candidatos:
        periodo = min(candidatos, key=lambda p: p.limite_gozo or date.max)
    return agregado, periodo


def coletar_itens(hoje, config):
    """Funcionários ativos cujo status entra nas regras, ordenados por urgência.

    Cada item: ``nome, empresa, setor, status (chave), status_label, dias,
    limite``. ``dias`` é o saldo (dias restantes) do período representativo.
    """
    habilitados = _status_habilitados(config)
    if not habilitados:
        return []

    funcionarios = (
        Funcionario.query.filter(Funcionario.ativo.is_(True))
        .options(
            selectinload(Funcionario.periodos),
            selectinload(Funcionario.programacoes),
        )
        .all()
    )

    itens = []
    for f in funcionarios:
        agregado, periodo = _periodo_representativo(f, hoje, config.antecedencia_dias)
        if agregado not in habilitados:
            continue
        limite = periodo.limite_gozo if periodo else None
        itens.append(
            {
                "nome": f.nome,
                "empresa": f.empresa.nome if f.empresa else "",
                "setor": f.setor.nome if f.setor else "—",
                "status": agregado,
                "status_label": status.LABELS[agregado],
                "dias": _fmt_dias(periodo.dias_restantes if periodo else None),
                "limite": limite.strftime("%d/%m/%Y") if limite else "—",
                "_ord_limite": limite or date.max,
            }
        )

    ordem = {s: i for i, s in enumerate(status.PRECEDENCIA)}
    itens.sort(key=lambda it: (ordem[it["status"]], it["_ord_limite"], it["nome"]))
    return itens


def montar_mensagem(config, itens, hoje, forcar=False):
    """Renderiza o resumo.

    Retorna ``None`` quando não há itens e ``enviar_se_vazio`` está off — salvo
    ``forcar=True`` (usado pelo "enviar teste", que sempre devolve uma mensagem).
    """
    data_str = hoje.strftime("%d/%m/%Y")

    if not itens:
        if not config.enviar_se_vazio and not forcar:
            return None
        return _render(config.modelo_sem_pendencias, {"data": data_str})

    visiveis = itens[:MAX_LINHAS]
    linhas = [
        _render(
            config.modelo_linha,
            {
                "nome": it["nome"],
                "empresa": it["empresa"],
                "setor": it["setor"],
                "status": it["status_label"],
                "dias": it["dias"],
                "limite": it["limite"],
            },
        )
        for it in visiveis
    ]
    corpo = "\n".join(linhas)
    if len(itens) > MAX_LINHAS:
        corpo += f"\n…e mais {len(itens) - MAX_LINHAS}."

    cabecalho = _render(
        config.modelo_cabecalho, {"data": data_str, "total": len(itens)}
    )
    # Garante separação cabeçalho/corpo mesmo se o admin editar o modelo.
    return f"{cabecalho.rstrip(chr(10))}\n{corpo}"
