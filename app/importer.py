"""Importação idempotente da planilha Excel para o banco.

Lida com a estrutura multi-linha das abas de empresa: a primeira linha de um
funcionário tem código (A) + nome (C); linhas seguintes sem código mas com
início aquisitivo (Q) são períodos adicionais do mesmo funcionário.

Modo ``dry_run``: faz tudo dentro de uma transação e dá rollback no final,
permitindo conferir contagens (novos / atualizados / inalterados) e divergências
de consistência antes de gravar de verdade.
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

CAMPOS_FUNC = ("nome", "data_admissao", "vencto_ferias")
CAMPOS_PERIODO = (
    "fim", "dias_direito", "dias_restantes", "limite_gozo",
    "dias_abono", "decimo_terceiro",
)
CAMPOS_PROG = ("periodo_aquisitivo_id", "dias_gozo", "data_fim", "origem")


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


def _snapshot(obj, campos):
    return tuple(getattr(obj, c) for c in campos)


def _validar_periodo(p, ref, avisos):
    if p.fim and p.inicio:
        delta = (p.fim - p.inicio).days
        if not 300 <= delta <= 400:
            avisos.append(
                f"{ref}: período aquisitivo com {delta} dias "
                f"({p.inicio} → {p.fim}); esperado ~365"
            )
    if p.fim and p.limite_gozo:
        delta = (p.limite_gozo - p.fim).days
        if delta < 0:
            avisos.append(
                f"{ref}: limite_gozo {p.limite_gozo} anterior ao fim {p.fim}"
            )
        elif not 300 <= delta <= 400:
            avisos.append(
                f"{ref}: limite_gozo {delta} dias após o fim ({p.fim} → "
                f"{p.limite_gozo}); esperado ~365"
            )
    if p.dias_direito is not None and p.dias_restantes is not None:
        if p.dias_restantes > p.dias_direito:
            avisos.append(
                f"{ref}: dias_restantes ({p.dias_restantes}) > "
                f"dias_direito ({p.dias_direito})"
            )


def _validar_programacao(prog, periodo, ref, avisos):
    if periodo.fim and prog.data_inicio < periodo.fim:
        avisos.append(
            f"{ref}: gozo em {prog.data_inicio} antes do fim do aquisitivo "
            f"({periodo.fim})"
        )
    if periodo.limite_gozo and prog.data_inicio > periodo.limite_gozo:
        avisos.append(
            f"{ref}: gozo em {prog.data_inicio} após o limite "
            f"({periodo.limite_gozo})"
        )


def importar_xlsx(caminho, dry_run=False):
    """Importa a planilha. Retorna relatório estruturado.

    Quando ``dry_run=True``, dá rollback no final em vez de commit — os
    contadores e avisos refletem o que *seria* gravado.
    """
    wb = load_workbook(caminho, data_only=True, read_only=True)

    contadores = {
        e: {"novos": 0, "atualizados": 0, "inalterados": 0}
        for e in ("empresas", "funcionarios", "periodos", "programacoes")
    }
    avisos = []

    def registrar(entidade, novo, antes, depois):
        if novo:
            contadores[entidade]["novos"] += 1
        elif antes != depois:
            contadores[entidade]["atualizados"] += 1
        else:
            contadores[entidade]["inalterados"] += 1

    for ws in wb.worksheets:
        if ws.title in ABAS_IGNORADAS:
            continue

        empresa, criada = _get_or_create(Empresa, nome=ws.title)
        if criada:
            db.session.flush()
        # Empresa não tem campos atualizáveis pelo importer.
        registrar("empresas", criada, (), ())

        funcionario_atual = None

        for linha_idx, row in enumerate(
            ws.iter_rows(min_row=PRIMEIRA_LINHA_DADOS, values_only=True),
            start=PRIMEIRA_LINHA_DADOS,
        ):
            def cell(key):
                idx = COL[key] - 1
                return row[idx] if idx < len(row) else None

            ref = f"{ws.title}:L{linha_idx}"
            codigo = _texto(cell("codigo"))
            q_inicio = to_date(cell("q_inicio"))

            if codigo:
                nome = _texto(cell("nome")) or "(sem nome)"
                funcionario_atual, novo = _get_or_create(
                    Funcionario, empresa_id=empresa.id, codigo=codigo
                )
                antes = _snapshot(funcionario_atual, CAMPOS_FUNC)
                funcionario_atual.nome = nome
                funcionario_atual.data_admissao = to_date(cell("admissao"))
                funcionario_atual.vencto_ferias = to_date(cell("vencto"))
                db.session.flush()
                depois = _snapshot(funcionario_atual, CAMPOS_FUNC)
                registrar("funcionarios", novo, antes, depois)
            elif q_inicio is None:
                continue  # linha em branco / separador

            if q_inicio is None or funcionario_atual is None:
                continue

            periodo, novo_p = _get_or_create(
                PeriodoAquisitivo,
                funcionario_id=funcionario_atual.id,
                inicio=q_inicio,
            )
            antes_p = _snapshot(periodo, CAMPOS_PERIODO)
            periodo.fim = to_date(cell("r_fim"))
            periodo.dias_direito = to_float(cell("ac_direito"))
            periodo.dias_restantes = to_float(cell("ag_restante"))
            periodo.limite_gozo = to_date(cell("ah_limite"))
            periodo.dias_abono = to_float(cell("z_abono"))
            periodo.decimo_terceiro = _texto(cell("ab_13"))
            db.session.flush()
            depois_p = _snapshot(periodo, CAMPOS_PERIODO)
            registrar("periodos", novo_p, antes_p, depois_p)
            _validar_periodo(periodo, ref, avisos)

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
                antes_pr = _snapshot(prog, CAMPOS_PROG)
                prog.periodo_aquisitivo_id = periodo.id
                prog.dias_gozo = dias_int
                prog.data_fim = (
                    w_inicio + timedelta(days=dias_int - 1) if dias_int else w_inicio
                )
                prog.origem = "import"
                depois_pr = _snapshot(prog, CAMPOS_PROG)
                registrar("programacoes", novo_prog, antes_pr, depois_pr)
                _validar_programacao(prog, periodo, ref, avisos)

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    wb.close()

    return {**contadores, "avisos": avisos, "dry_run": dry_run}
