"""Testes da programação de férias: consumo de saldo e validações."""
from datetime import date, timedelta

from app.models import (
    Empresa,
    Funcionario,
    PeriodoAquisitivo,
    ProgramacaoFerias,
    db,
)


def _setup_funcionario(saldo=16, setor_id=None):
    hoje = date.today()
    emp = Empresa(nome="Teste Ltda")
    db.session.add(emp)
    db.session.flush()
    f = Funcionario(
        empresa_id=emp.id, setor_id=setor_id, codigo="1", nome="FULANO DE TAL"
    )
    db.session.add(f)
    db.session.flush()
    p = PeriodoAquisitivo(
        funcionario_id=f.id,
        inicio=hoje - timedelta(days=400),
        fim=hoje - timedelta(days=35),     # fechado
        dias_direito=30,
        dias_restantes=saldo,
        limite_gozo=hoje + timedelta(days=200),
    )
    db.session.add(p)
    db.session.commit()
    return f, p


def test_programar_consome_saldo(app, client_gestor, gestor_comum):
    f, p = _setup_funcionario(saldo=16, setor_id=gestor_comum.setor_id)
    inicio = (date.today() + timedelta(days=45)).isoformat()

    r = client_gestor.post(
        f"/funcionarios/{f.id}/programar",
        data={"periodo_id": p.id, "data_inicio": inicio, "dias_gozo": 10},
        follow_redirects=True,
    )
    assert "programadas com sucesso" in r.get_data(as_text=True)

    p_atual = db.session.get(PeriodoAquisitivo, p.id)
    assert p_atual.dias_restantes == 6  # 16 - 10

    prog = ProgramacaoFerias.query.filter_by(funcionario_id=f.id).first()
    assert prog.criado_por_id == gestor_comum.id


def test_nao_programa_alem_do_saldo(app, client_gestor, gestor_comum):
    f, p = _setup_funcionario(saldo=6, setor_id=gestor_comum.setor_id)
    inicio = (date.today() + timedelta(days=45)).isoformat()

    r = client_gestor.post(
        f"/funcionarios/{f.id}/programar",
        data={"periodo_id": p.id, "data_inicio": inicio, "dias_gozo": 10},
        follow_redirects=True,
    )
    assert "excedem o saldo" in r.get_data(as_text=True)
    assert db.session.get(PeriodoAquisitivo, p.id).dias_restantes == 6  # inalterado


def test_aviso_previo_30_dias(app, client_gestor, gestor_comum):
    f, p = _setup_funcionario(saldo=16, setor_id=gestor_comum.setor_id)
    cedo = (date.today() + timedelta(days=5)).isoformat()

    r = client_gestor.post(
        f"/funcionarios/{f.id}/programar",
        data={"periodo_id": p.id, "data_inicio": cedo, "dias_gozo": 5},
        follow_redirects=True,
    )
    assert "antecedência" in r.get_data(as_text=True)
    assert db.session.get(PeriodoAquisitivo, p.id).dias_restantes == 16  # inalterado
