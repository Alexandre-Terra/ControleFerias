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


def test_admin_programa_sem_aviso_previo(app, client_admin, gestor_admin):
    # Admin é isento do aviso de 30 dias — pode marcar começando hoje.
    f, p = _setup_funcionario(saldo=16)
    hoje = date.today().isoformat()

    r = client_admin.post(
        f"/funcionarios/{f.id}/programar",
        data={"periodo_id": p.id, "data_inicio": hoje, "dias_gozo": 10},
        follow_redirects=True,
    )
    assert "programadas com sucesso" in r.get_data(as_text=True)
    assert db.session.get(PeriodoAquisitivo, p.id).dias_restantes == 6  # 16 - 10

    prog = ProgramacaoFerias.query.filter_by(funcionario_id=f.id).first()
    assert prog.criado_por_id == gestor_admin.id


def test_admin_nao_programa_no_passado(app, client_admin, gestor_admin):
    f, p = _setup_funcionario(saldo=16)
    ontem = (date.today() - timedelta(days=1)).isoformat()

    r = client_admin.post(
        f"/funcionarios/{f.id}/programar",
        data={"periodo_id": p.id, "data_inicio": ontem, "dias_gozo": 5},
        follow_redirects=True,
    )
    assert "não pode estar no passado" in r.get_data(as_text=True)
    assert db.session.get(PeriodoAquisitivo, p.id).dias_restantes == 16  # inalterado


def test_form_admin_sem_aviso_minimo_hoje(app, client_admin, gestor_admin):
    # GET: admin vê a caixa informativa da isenção e min do input = hoje.
    f, p = _setup_funcionario(saldo=16)

    r = client_admin.get(f"/funcionarios/{f.id}/programar")
    html = r.get_data(as_text=True)
    assert "sem exigência de aviso prévio" in html
    assert f'min="{date.today().isoformat()}"' in html


def test_form_gestor_comum_minimo_30_dias(app, client_gestor, gestor_comum):
    # GET: gestor comum segue vendo o aviso de 30 dias e min = hoje + 30.
    f, p = _setup_funcionario(saldo=16, setor_id=gestor_comum.setor_id)

    r = client_gestor.get(f"/funcionarios/{f.id}/programar")
    html = r.get_data(as_text=True)
    assert "Aviso prévio de 30 dias" in html
    assert f'min="{(date.today() + timedelta(days=30)).isoformat()}"' in html


def _programacao(f, p, inicio, dias, origem="manual", criado_por_id=None):
    prog = ProgramacaoFerias(
        funcionario_id=f.id,
        periodo_aquisitivo_id=p.id if p else None,
        data_inicio=inicio,
        dias_gozo=dias,
        data_fim=inicio + timedelta(days=dias - 1),
        origem=origem,
        criado_por_id=criado_por_id,
    )
    db.session.add(prog)
    db.session.commit()
    return prog


def test_cancelar_restaura_saldo_e_remove(app, client_gestor, gestor_comum):
    # Saldo 6 = 16 originais já consumidos pela programação de 10 dias.
    f, p = _setup_funcionario(saldo=6, setor_id=gestor_comum.setor_id)
    prog = _programacao(
        f, p, date.today() + timedelta(days=45), 10,
        criado_por_id=gestor_comum.id,
    )
    pid = prog.id

    r = client_gestor.post(
        f"/funcionarios/{f.id}/programacoes/{pid}/cancelar",
        follow_redirects=True,
    )
    assert "cancelada" in r.get_data(as_text=True)
    assert db.session.get(PeriodoAquisitivo, p.id).dias_restantes == 16
    assert db.session.get(ProgramacaoFerias, pid) is None


def test_cancelar_import_em_curso_sem_criador(app, client_gestor, gestor_comum):
    # Espelha o caso real: prog importada em curso, saldo zerado pela planilha.
    f, p = _setup_funcionario(saldo=0, setor_id=gestor_comum.setor_id)
    prog = _programacao(
        f, p, date.today() - timedelta(days=9), 30, origem="import"
    )
    pid = prog.id

    r = client_gestor.post(
        f"/funcionarios/{f.id}/programacoes/{pid}/cancelar",
        follow_redirects=True,
    )
    assert "Saldo do período restaurado" in r.get_data(as_text=True)
    assert db.session.get(PeriodoAquisitivo, p.id).dias_restantes == 30
    assert db.session.get(ProgramacaoFerias, pid) is None


def test_cancelar_403_fora_do_escopo(app, client_gestor, gestor_comum):
    f, p = _setup_funcionario(saldo=6, setor_id=None)  # fora do setor do gestor
    prog = _programacao(f, p, date.today() + timedelta(days=45), 10)

    r = client_gestor.post(
        f"/funcionarios/{f.id}/programacoes/{prog.id}/cancelar"
    )
    assert r.status_code == 403
    assert db.session.get(ProgramacaoFerias, prog.id) is not None


def test_cancelar_404_prog_de_outro_funcionario(app, client_gestor, gestor_comum):
    f, p = _setup_funcionario(saldo=6, setor_id=gestor_comum.setor_id)
    f2 = Funcionario(
        empresa_id=f.empresa_id, setor_id=gestor_comum.setor_id,
        codigo="2", nome="BELTRANO DE TAL",
    )
    db.session.add(f2)
    db.session.commit()
    prog2 = _programacao(f2, None, date.today() + timedelta(days=45), 10)

    r = client_gestor.post(
        f"/funcionarios/{f.id}/programacoes/{prog2.id}/cancelar"
    )
    assert r.status_code == 404
    assert db.session.get(ProgramacaoFerias, prog2.id) is not None
    assert db.session.get(PeriodoAquisitivo, p.id).dias_restantes == 6


def test_cancelar_passada_proibido(app, client_gestor, gestor_comum):
    f, p = _setup_funcionario(saldo=6, setor_id=gestor_comum.setor_id)
    prog = _programacao(f, p, date.today() - timedelta(days=40), 10)  # fim no passado

    r = client_gestor.post(
        f"/funcionarios/{f.id}/programacoes/{prog.id}/cancelar",
        follow_redirects=True,
    )
    assert "já encerrada" in r.get_data(as_text=True)
    assert db.session.get(ProgramacaoFerias, prog.id) is not None
    assert db.session.get(PeriodoAquisitivo, p.id).dias_restantes == 6


def test_cancelar_sem_periodo_vinculado(app, client_gestor, gestor_comum):
    f, p = _setup_funcionario(saldo=6, setor_id=gestor_comum.setor_id)
    prog = _programacao(f, None, date.today() + timedelta(days=45), 10)
    pid = prog.id

    r = client_gestor.post(
        f"/funcionarios/{f.id}/programacoes/{pid}/cancelar",
        follow_redirects=True,
    )
    texto = r.get_data(as_text=True)
    assert "cancelada" in texto
    assert "restaurado" not in texto
    assert db.session.get(ProgramacaoFerias, pid) is None
    assert db.session.get(PeriodoAquisitivo, p.id).dias_restantes == 6
