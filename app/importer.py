"""Importação idempotente da planilha Excel para o banco.

Lida com a estrutura multi-linha das abas de empresa: a primeira linha de um
funcionário tem código (A) + nome (C); linhas seguintes sem código mas com
início aquisitivo (Q) são períodos adicionais do mesmo funcionário.
"""
from datetime import date, datetime, timedelta

from openpyxl import load_workbook

from .models import Empresa, Funcionario, PeriodoAquisitivo, ProgramacaoFerias, db

EXCEL_EPOCH = date(1899, 12, 30)

ABAS_IGNORADAS = {"DASHBOARD", "Resumo"}
PRIMEIRA_LINHA_DADOS = 8

# Índices de coluna (1-based) conforme o cabeçalho das abas de empresa.
COL = {
    "codigo": 1,    # A
    "nome": 3,      # C
    "admissao": 10, # J
    "vencto": 11,   # K
    "q_inicio": 17, # Q - início aquisitivo
    "r_fim": 18,    # R - fim aquisitivo
    "w_gozo": 23,   # W - início gozo
    "x_dias": 24,   # X - dias de gozo
    "z_abono": 26,  # Z - abono
    "ab_13": 28,    # AB - 13º
    "ac_direito": 29,   # AC - dias de direito
    "ag_restante": 33,  # AG - dias restantes
    "ah_limite": 34,    # AH - limite p/ gozo
}


def to_date(v):
    """Converte serial Excel / datetime / string em date, ou None."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)):
        return EXCEL_EPOCH + timedelta(days=int(v)) if v > 0 else None
    s = str(v).strip()
    if not s or set(s) <= set("./ -"):  # ex.: "..../..../......"
        return None
    try:
        return EXCEL_EPOCH + timedelta(days=int(float(s.replace(",", "."))))
    except ValueError:
        return None


def to_float(v):
    """Converte número / string (vírgula ou ponto) em float, ou None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", ".")
    if not s or set(s) <= set("./ -"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _texto(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _get_or_create(model, defaults=None, **filtros):
    obj = db.session.query(model).filter_by(**filtros).first()
    if obj is None:
        obj = model(**filtros, **(defaults or {}))
        db.session.add(obj)
        criado = True
    else:
        criado = False
    return obj, criado


def importar_xlsx(caminho):
    """Importa a planilha. Retorna dicionário com contagens."""
    wb = load_workbook(caminho, data_only=True, read_only=True)
    stats = {"empresas": 0, "funcionarios": 0, "periodos": 0, "programacoes": 0}

    for ws in wb.worksheets:
        if ws.title in ABAS_IGNORADAS:
            continue

        empresa, criada = _get_or_create(Empresa, nome=ws.title)
        if criada:
            db.session.flush()
            stats["empresas"] += 1

        funcionario_atual = None

        for row in ws.iter_rows(min_row=PRIMEIRA_LINHA_DADOS, values_only=True):
            def cell(key):
                idx = COL[key] - 1
                return row[idx] if idx < len(row) else None

            codigo = _texto(cell("codigo"))
            q_inicio = to_date(cell("q_inicio"))

            if codigo:
                nome = _texto(cell("nome")) or "(sem nome)"
                funcionario_atual, novo = _get_or_create(
                    Funcionario, empresa_id=empresa.id, codigo=codigo
                )
                funcionario_atual.nome = nome
                funcionario_atual.data_admissao = to_date(cell("admissao"))
                funcionario_atual.vencto_ferias = to_date(cell("vencto"))
                db.session.flush()
                if novo:
                    stats["funcionarios"] += 1
            elif q_inicio is None:
                continue  # linha em branco / separador

            if q_inicio is None or funcionario_atual is None:
                continue

            periodo, novo_p = _get_or_create(
                PeriodoAquisitivo,
                funcionario_id=funcionario_atual.id,
                inicio=q_inicio,
            )
            periodo.fim = to_date(cell("r_fim"))
            periodo.dias_direito = to_float(cell("ac_direito"))
            periodo.dias_restantes = to_float(cell("ag_restante"))
            periodo.limite_gozo = to_date(cell("ah_limite"))
            periodo.dias_abono = to_float(cell("z_abono"))
            periodo.decimo_terceiro = _texto(cell("ab_13"))
            db.session.flush()
            if novo_p:
                stats["periodos"] += 1

            # Programação de férias já existente (coluna W com data).
            w_inicio = to_date(cell("w_gozo"))
            if w_inicio:
                dias = to_float(cell("x_dias"))
                dias_int = int(dias) if dias else 0
                prog, novo_prog = _get_or_create(
                    ProgramacaoFerias,
                    funcionario_id=funcionario_atual.id,
                    data_inicio=w_inicio,
                )
                prog.periodo_aquisitivo_id = periodo.id
                prog.dias_gozo = dias_int
                prog.data_fim = (
                    w_inicio + timedelta(days=dias_int - 1) if dias_int else w_inicio
                )
                prog.origem = "import"
                if novo_prog:
                    stats["programacoes"] += 1

    db.session.commit()
    wb.close()
    return stats
