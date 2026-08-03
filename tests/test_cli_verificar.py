"""Smoke do comando `flask verificar-saldos` (instrumento de conferência)."""
from datetime import date, timedelta

from app.models import Empresa, Funcionario, PeriodoAquisitivo, db


def test_verificar_saldos_acusa_caso_congelado(app):
    # O caso do bug em prod: AG congelado (27,5) num período que fechou depois
    # do retrato — o comando tem de mostrar saldo=30 e contá-lo no resumo.
    emp = Empresa(nome="ACME")
    db.session.add(emp)
    db.session.flush()
    f = Funcionario(empresa_id=emp.id, codigo="1", nome="FULANO DE TAL")
    db.session.add(f)
    db.session.flush()
    hoje = date.today()
    db.session.add(PeriodoAquisitivo(
        funcionario_id=f.id,
        inicio=hoje - timedelta(days=400),
        fim=hoje - timedelta(days=35),
        dias_direito=27.5,
        saldo_snapshot=27.5,
        snapshot_em=hoje - timedelta(days=60),  # retrato ANTES de fechar
        limite_gozo=hoje + timedelta(days=330),
    ))
    db.session.commit()

    r = app.test_cli_runner().invoke(args=["verificar-saldos"])
    assert r.exit_code == 0
    assert "saldo=30" in r.output            # derivado, não o 27,5 congelado
    assert "(-> 30): 1" in r.output          # resumo acusa o caso
    assert "[virtual" in r.output            # janela seguinte aparece
    # read-only: nada mudou no banco
    assert PeriodoAquisitivo.query.count() == 1
