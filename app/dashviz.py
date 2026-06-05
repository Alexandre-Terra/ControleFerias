"""Agregações para o painel de risco (dataviz do redesenho).

Consome ``app.status`` (que permanece puro, sem DB e sem apresentação) e produz
os números/coordenadas que os gráficos do dashboard precisam. Todas as reduções
são protegidas contra base vazia (divisões por zero, ``max`` de lista vazia).
"""
import calendar
import math
from datetime import date

from . import status as st

MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
         "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


# ---- helpers de data -------------------------------------------------------
def _add_months(ano, mes, n):
    """Retorna (ano, mes) deslocado em ``n`` meses."""
    idx = (ano * 12 + (mes - 1)) + n
    return idx // 12, idx % 12 + 1


def _ultimo_dia(ano, mes):
    return calendar.monthrange(ano, mes)[1]


def _curto(empresa):
    """Rótulo curto da empresa (primeira palavra do nome)."""
    nome = empresa.nome if empresa else "—"
    return nome.split()[0] if nome else "—"


def dias_para_limite(funcionario, hoje, dav):
    """Dias até o prazo de gozo mais próximo entre períodos em risco/direito.

    Negativo = já vencido. ``None`` se não há prazo aplicável.
    """
    lims = [
        (p.limite_gozo - hoje).days
        for p, s in st.periodos_com_status(funcionario, hoje, dav)
        if s in (st.VENCIDA, st.A_VENCER, st.TEM_DIREITO) and p.limite_gozo
    ]
    return min(lims) if lims else None


# ---- agregação principal ---------------------------------------------------
def dashboard_dados(funcionarios, hoje, dav):
    """Tudo que o template do painel precisa, já calculado e protegido."""
    # contagens por status
    counts = {s: 0 for s in st.PRECEDENCIA}
    com_status = []
    for f in funcionarios:
        agg = st.status_funcionario(f, hoje, dav)
        counts[agg] += 1
        com_status.append((f, agg))

    total = len(funcionarios)

    return {
        "counts": counts,
        "total": total,
        "dav": dav,
        "empresas": len({f.empresa_id for f in funcionarios}),
        "total_atencao": counts[st.VENCIDA] + counts[st.A_VENCER],
        "donut": _donut(counts, total),
        "timeline": _timeline(funcionarios, hoje, dav),
        "heatmap": _heatmap(funcionarios, hoje, dav),
        "trend": _trend(funcionarios, hoje),
        "proximos": _proximos(funcionarios, hoje, dav),
        "risco": _risco(com_status, funcionarios, hoje, dav),
    }


# ---- donut -----------------------------------------------------------------
def _donut(counts, total, size=184):
    """Segmentos do donut (stroke-dasharray pré-calculado)."""
    if total <= 0:
        return {"size": size, "r": size / 2 - 16, "c": 0, "segments": []}
    r = size / 2 - 16
    c = 2 * math.pi * r
    acc = 0.0
    segments = []
    for s in st.PRECEDENCIA:
        n = counts[s]
        if n <= 0:
            continue
        seg = (n / total) * c
        segments.append({
            "status": s,
            "var": st.VAR[s],
            "n": n,
            "len": max(0.0, seg - 2.5),
            "off": acc,
            "c": c,
        })
        acc += seg
    return {"size": size, "r": r, "c": c, "segments": segments}


# ---- timeline (calendário de férias) ---------------------------------------
def _timeline(funcionarios, hoje, dav):
    """Janela de 7 meses a partir do mês atual; barras das programações futuras."""
    start = date(hoje.year, hoje.month, 1)
    ey, em = _add_months(hoje.year, hoje.month, 6)
    end = date(ey, em, _ultimo_dia(ey, em))
    total_days = max(1, (end - start).days)

    def pct(d):
        return max(0.0, min(100.0, (d - start).days / total_days * 100))

    meses = []
    for i in range(7):
        my, mm = _add_months(hoje.year, hoje.month, i)
        meses.append({"label": MESES[mm - 1].upper(), "left": pct(date(my, mm, 1))})

    rows = []
    for f in funcionarios:
        agg = st.status_funcionario(f, hoje, dav)
        for prog in f.programacoes:
            fim = prog.data_fim or prog.data_inicio
            if not fim or fim < hoje or prog.data_inicio > end:
                continue
            left = pct(prog.data_inicio)
            width = max(2.5, pct(fim) - left)
            rows.append({
                "nome": f.nome,
                "empresa": _curto(f.empresa),
                "status": agg,
                "left": left,
                "width": width,
                "dias": prog.dias_gozo,
                "inicio": prog.data_inicio,
                "fim": fim,
            })
    rows.sort(key=lambda r: r["inicio"])
    return {"meses": meses, "hoje_pct": pct(hoje), "rows": rows}


# ---- heatmap (mapa de prazos) ----------------------------------------------
def _heatmap(funcionarios, hoje, dav):
    """Empresa × mês dos prazos de gozo + coluna de atraso."""
    # meses: atual+1 .. atual+6
    meses = []
    for i in range(1, 7):
        my, mm = _add_months(hoje.year, hoje.month, i)
        meses.append({"ano": my, "mes": mm, "label": MESES[mm - 1].upper()})

    # coleta prazos (limite_gozo) de períodos em risco/direito
    prazos = []  # (empresa_id, dias, ano, mes)
    empresas = {}
    for f in funcionarios:
        if f.empresa:
            empresas.setdefault(f.empresa.id, f.empresa)
        for p, s in st.periodos_com_status(f, hoje, dav):
            if s in (st.VENCIDA, st.A_VENCER, st.TEM_DIREITO) and p.limite_gozo:
                d = (p.limite_gozo - hoje).days
                prazos.append((f.empresa_id, d, p.limite_gozo.year, p.limite_gozo.month))

    def cell_count(emp_id, kind):
        if kind == "overdue":
            return sum(1 for (e, d, _y, _m) in prazos if e == emp_id and d < 0)
        ano, mes = kind
        return sum(1 for (e, d, y, m) in prazos
                   if e == emp_id and d >= 0 and y == ano and m == mes)

    emp_list = sorted(empresas.values(), key=lambda e: e.nome)
    all_counts = []
    grid = []
    for e in emp_list:
        overdue = cell_count(e.id, "overdue")
        month_cells = [cell_count(e.id, (mo["ano"], mo["mes"])) for mo in meses]
        all_counts.append(overdue)
        all_counts.extend(month_cells)
        grid.append({"empresa": e.nome, "overdue": overdue, "months": month_cells})

    max_v = max([1] + all_counts)

    def tile(n, overdue):
        if n == 0:
            return {"n": 0, "pct": 0, "overdue": overdue, "empty": True}
        inten = 0.18 + 0.62 * (n / max_v)
        return {"n": n, "pct": round(inten * 100), "overdue": overdue,
                "strong": inten > 0.5, "empty": False}

    rows = []
    for row in grid:
        rows.append({
            "empresa": row["empresa"],
            "overdue": tile(row["overdue"], True),
            "months": [tile(n, False) for n in row["months"]],
        })
    return {"meses": meses, "rows": rows}


# ---- trend (programadas por mês) -------------------------------------------
def _trend(funcionarios, hoje):
    meses = [_add_months(hoje.year, hoje.month, i) for i in range(7)]
    counts = []
    for (y, mo) in meses:
        n = 0
        for f in funcionarios:
            for prog in f.programacoes:
                di = prog.data_inicio
                if di and di.year == y and di.month == mo:
                    n += 1
        counts.append(n)
    max_v = max([1] + counts)
    bars = []
    for (y, mo), n in zip(meses, counts):
        bars.append({"label": MESES[mo - 1].upper(), "n": n,
                     "h": round((n / max_v) * 84 + 4) if n else 4})
    return bars


# ---- próximos prazos -------------------------------------------------------
def _proximos(funcionarios, hoje, dav, limite=5):
    out = []
    for f in funcionarios:
        for p, s in st.periodos_com_status(f, hoje, dav):
            if s in (st.VENCIDA, st.A_VENCER, st.TEM_DIREITO) and p.limite_gozo:
                dias = (p.limite_gozo - hoje).days
                if dias >= 0:
                    out.append({"f_id": f.id, "nome": f.nome,
                                "empresa": _curto(f.empresa), "status": s,
                                "data": p.limite_gozo, "dias": dias})
    out.sort(key=lambda x: x["data"])
    return out[:limite]


# ---- lista de risco priorizada ---------------------------------------------
def _risco(com_status, funcionarios, hoje, dav):
    out = []
    for f, agg in com_status:
        if agg in (st.VENCIDA, st.A_VENCER):
            out.append({
                "f_id": f.id, "nome": f.nome, "codigo": f.codigo,
                "empresa": _curto(f.empresa),
                "setor": f.setor.nome if f.setor else "—",
                "status": agg,
                "dias": dias_para_limite(f, hoje, dav),
            })
    out.sort(key=lambda x: x["dias"] if x["dias"] is not None else 10 ** 9)
    return out
