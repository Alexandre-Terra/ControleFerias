"""Testes do importador: conversões, parsing multi-linha e idempotência."""
from datetime import date

from openpyxl import Workbook

from app.importer import (
    COL,
    EXCEL_EPOCH,
    importar_xlsx,
    to_date,
    to_float,
)
from app.models import Funcionario, PeriodoAquisitivo, ProgramacaoFerias


def serial(d):
    return (d - EXCEL_EPOCH).days


def test_to_date_variantes():
    assert to_date(serial(date(2024, 8, 1))) == date(2024, 8, 1)
    assert to_date(date(2024, 8, 1)) == date(2024, 8, 1)
    assert to_date("..../..../......") is None
    assert to_date(None) is None


def test_to_float_virgula_e_ponto():
    assert to_float("7,5") == 7.5
    assert to_float("30") == 30.0
    assert to_float(22.5) == 22.5
    assert to_float("-") is None
    assert to_float("") is None


def _planilha(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Auto Mec"  # aba de empresa (não ignorada)

    def put(row, key, value):
        ws.cell(row=row, column=COL[key], value=value)

    # Linha 8: funcionário com 1º período (fechado) + programação (W).
    put(8, "codigo", 3)
    put(8, "nome", "DOUGLAS SOUSA DA SILVA")
    put(8, "admissao", serial(date(2015, 10, 1)))
    put(8, "q_inicio", serial(date(2024, 10, 1)))
    put(8, "r_fim", serial(date(2025, 9, 30)))
    put(8, "ac_direito", 30)
    put(8, "ag_restante", 16)
    put(8, "ah_limite", serial(date(2026, 9, 15)))
    put(8, "w_gozo", serial(date(2026, 7, 1)))
    put(8, "x_dias", 16)

    # Linha 9: continuação (SEM código) -> 2º período do mesmo funcionário.
    put(9, "q_inicio", serial(date(2025, 10, 1)))
    put(9, "r_fim", serial(date(2026, 9, 30)))
    put(9, "ac_direito", "7,5")  # decimal com vírgula
    put(9, "ag_restante", "7,5")

    caminho = tmp_path / "mini.xlsx"
    wb.save(caminho)
    return caminho


def test_import_multilinha_e_conversoes(app, tmp_path):
    caminho = _planilha(tmp_path)
    stats = importar_xlsx(str(caminho))

    assert stats == {
        "empresas": 1,
        "funcionarios": 1,
        "periodos": 2,
        "programacoes": 1,
    }

    f = Funcionario.query.filter_by(codigo="3").one()
    assert f.nome == "DOUGLAS SOUSA DA SILVA"
    assert f.data_admissao == date(2015, 10, 1)
    assert len(f.periodos) == 2

    p2 = PeriodoAquisitivo.query.filter_by(inicio=date(2025, 10, 1)).one()
    assert p2.dias_direito == 7.5  # vírgula convertida

    prog = ProgramacaoFerias.query.one()
    assert prog.data_inicio == date(2026, 7, 1)
    assert prog.data_fim == date(2026, 7, 16)  # início + 16 - 1
    assert prog.origem == "import"


def test_import_idempotente(app, tmp_path):
    caminho = _planilha(tmp_path)
    importar_xlsx(str(caminho))
    stats2 = importar_xlsx(str(caminho))  # segunda vez não cria nada

    assert stats2 == {
        "empresas": 0,
        "funcionarios": 0,
        "periodos": 0,
        "programacoes": 0,
    }
    assert Funcionario.query.count() == 1
    assert PeriodoAquisitivo.query.count() == 2
