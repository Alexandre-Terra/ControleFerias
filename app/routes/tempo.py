"""Página "Tempo Funcionários" (admin) — marcos por data de admissão.

Mostra, para cada colaborador ativo, o tempo de casa, o último marco já batido
e o próximo (45/90/120 dias e aniversários, ver ``app/tempo.py``), além de
destacar os marcos cujo aviso cai hoje — exatamente os que entram no resumo do
WhatsApp. Apenas admin: a visão é da empresa toda, sem recorte por setor.

Duas leituras do mesmo conjunto, alternadas por ``?vista=``:

- ``colaborador`` (padrão): uma linha por pessoa, último e próximo marco;
- ``linha``: uma linha por marco **do mês selecionado**, batidos e a bater
  juntos em ordem de data.

O mês (``?mes=AAAA-MM``, padrão o corrente) governa o painel-resumo e a vista
de linha do tempo. Os filtros recortam a tabela e o resumo do mês; o painel
"Avisos de hoje" segue sobre **todos** — ele espelha o disparo do WhatsApp, que
não conhece filtro de tela.
"""
from datetime import date

from flask import Blueprint, render_template, request, url_for
from sqlalchemy.orm import joinedload

from ..auth import admin_required
from ..models import ConfiguracaoZapi, Empresa, Funcionario, Setor
from .. import tempo as tp

bp = Blueprint("tempo", __name__, url_prefix="/tempo-funcionarios")

# Filtro por tipo de marco: (valor na URL, rótulo no chip).
MARCO_OPCOES = [
    ("45", "45 dias"),
    ("90", "90 dias"),
    ("120", "120 dias"),
    (tp.CHAVE_ANIVERSARIO, "Aniversário"),
]

VISTAS = ("colaborador", "linha")


def _parse_mes(valor, hoje):
    """``"AAAA-MM"`` → primeiro dia do mês; qualquer lixo cai no mês corrente."""
    try:
        ano, mes = valor.split("-")
        return date(int(ano), int(mes), 1)
    except (AttributeError, ValueError):
        return hoje.replace(day=1)


def _args(filtros, **troca):
    """Query args atuais com as substituições de ``troca`` (``None`` remove)."""
    args = {
        "busca": filtros["busca"] or None,
        "empresa": filtros["empresa"] or None,
        "setor": filtros["setor"] or None,
        "faixa": filtros["faixa"] or None,
        "marco": filtros["marco"] or None,
        "mes": filtros["mes"] or None,
        "vista": filtros["vista"] if filtros["vista"] != VISTAS[0] else None,
        "no_mes": "1" if filtros["no_mes"] else None,
    }
    args.update(troca)
    return {k: v for k, v in args.items() if v is not None}


@bp.route("/")
@admin_required
def index():
    hoje = date.today()

    busca = (request.args.get("busca") or "").strip()
    empresa_id = request.args.get("empresa", type=int)
    setor_id = request.args.get("setor", type=int)
    faixa = (request.args.get("faixa") or "").strip()
    # Múltipla escolha; `getlist` também aceita as URLs antigas (?marco=45).
    marcos_sel = [m for m in request.args.getlist("marco") if m in dict(MARCO_OPCOES)]
    vista = request.args.get("vista") if request.args.get("vista") in VISTAS else VISTAS[0]
    no_mes = request.args.get("no_mes") == "1"

    mes_ref = _parse_mes(request.args.get("mes"), hoje)
    ini_mes, fim_mes = tp.janela_mes(mes_ref)

    funcionarios = (
        Funcionario.query.filter(Funcionario.ativo.is_(True))
        .options(joinedload(Funcionario.empresa), joinedload(Funcionario.setor))
        .order_by(Funcionario.nome)
        .all()
    )

    linhas = []
    alertas_hoje = []
    sem_admissao = 0
    for f in funcionarios:
        if f.data_admissao is None:
            sem_admissao += 1
            continue
        ultimo = tp.ultimo_marco(f.data_admissao, hoje)
        linhas.append(
            {
                "f": f,
                "ultimo": ultimo,
                "ultimo_ha": tp.descricao_desde(ultimo["data"], hoje) if ultimo else None,
                "proximo": tp.proximo_marco(f.data_admissao, hoje),
                "tempo_casa": tp.descricao_tempo_casa(f.data_admissao, hoje),
                "faixa": tp.faixa_tempo_casa(f.data_admissao, hoje),
                "marcos_mes": tp.marcos_no_intervalo(f.data_admissao, ini_mes, fim_mes, hoje),
            }
        )
        for mk in tp.alertas_do_dia(f.data_admissao, hoje):
            alertas_hoje.append({"f": f, "marco": mk})

    # Total de colaboradores com admissão (antes de aplicar os filtros da tabela).
    total_com_admissao = len(linhas)

    # Filtros de identidade (em Python, sobre o conjunto já carregado) — o painel
    # "Avisos de hoje" e a contagem "sem admissão" seguem sobre todos.
    if busca:
        b = busca.lower()
        linhas = [l for l in linhas
                  if b in l["f"].nome.lower() or b in (l["f"].codigo or "").lower()]
    if empresa_id:
        linhas = [l for l in linhas if l["f"].empresa_id == empresa_id]
    if setor_id:
        linhas = [l for l in linhas if l["f"].setor_id == setor_id]
    if faixa:
        linhas = [l for l in linhas if l["faixa"] == faixa]

    # Eventos do mês: a linha do tempo em si e a base do resumo. Recortados pelos
    # filtros de identidade acima e pelos chips de tipo — nunca pelo "próximo
    # marco", senão o resumo do mês passaria a depender do que vem depois dele.
    eventos = [
        {"f": l["f"], "marco": mk}
        for l in linhas
        for mk in l["marcos_mes"]
        if not marcos_sel or mk["chave"] in marcos_sel
    ]
    eventos.sort(key=lambda e: (e["marco"]["data"], e["f"].nome))
    resumo = tp.resumo_marcos([e["marco"] for e in eventos])

    # Na vista por colaborador os chips filtram "o marco em foco" de cada linha:
    # os marcos do mês quando se pediu só quem tem marco no mês, senão o próximo.
    if vista == "colaborador":
        if no_mes:
            linhas = [l for l in linhas if l["marcos_mes"]]
        if marcos_sel:
            def em_foco(l):
                return l["marcos_mes"] if no_mes else [l["proximo"]]

            linhas = [l for l in linhas
                      if any(mk["chave"] in marcos_sel for mk in em_foco(l))]

    linhas.sort(key=lambda l: l["proximo"]["data"])
    alertas_hoje.sort(key=lambda a: (a["marco"]["data"], a["f"].nome))

    filtros = {
        "busca": busca,
        "empresa": empresa_id,
        "setor": setor_id,
        "faixa": faixa,
        "marco": marcos_sel,
        "mes": f"{mes_ref.year:04d}-{mes_ref.month:02d}",
        "vista": vista,
        "no_mes": no_mes,
    }

    def _url(**troca):
        return url_for("tempo.index", **_args(filtros, **troca))

    def _mes(n):
        d = tp.desloca_mes(mes_ref, n)
        return f"{d.year:04d}-{d.month:02d}"

    def _alterna_marco(chave):
        """URL do chip: tira a chave se já está ligada, senão acrescenta."""
        if chave in marcos_sel:
            return _url(marco=[m for m in marcos_sel if m != chave] or None)
        return _url(marco=marcos_sel + [chave])

    nav = {
        "mes_anterior": _url(mes=_mes(-1)),
        "mes_seguinte": _url(mes=_mes(1)),
        "mes_hoje": _url(mes=f"{hoje.year:04d}-{hoje.month:02d}"),
        "vistas": {v: _url(vista=v if v != VISTAS[0] else None) for v in VISTAS},
        "no_mes": _url(no_mes=None if no_mes else "1"),
        "marcos": {chave: _alterna_marco(chave) for chave, _rotulo in MARCO_OPCOES},
        "limpar_marcos": _url(marco=None),
    }

    cfg = ConfiguracaoZapi.obter()
    return render_template(
        "tempo_funcionarios.html",
        linhas=linhas,
        eventos=eventos,
        resumo=resumo,
        vista=vista,
        mes_ref=mes_ref,
        mes_label=tp.label_mes(mes_ref),
        mes_corrente=mes_ref == hoje.replace(day=1),
        alertas_hoje=alertas_hoje,
        sem_admissao=sem_admissao,
        total_com_admissao=total_com_admissao,
        empresas=Empresa.query.order_by(Empresa.nome).all(),
        setores=Setor.query.order_by(Setor.nome).all(),
        marco_opcoes=MARCO_OPCOES,
        faixas=tp.FAIXAS_TEMPO,
        filtros=filtros,
        nav=nav,
        zapi_ativo=cfg.pronta() and cfg.notificar_tempo_servico,
    )
