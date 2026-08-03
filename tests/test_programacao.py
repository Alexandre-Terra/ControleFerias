"""Testes da programação de férias: consumo de saldo derivado e validações.

O saldo nunca é mutado na coluna: programar cria a linha (que já desconta no
saldo derivado) e cancelar a apaga (que já devolve). ``saldo_snapshot`` fica
intacto em todos os cenários — os asserts conferem os dois lados.
"""
from datetime import date, timedelta

from app import status as st
from app.models import (
    Empresa,
    Funcionario,
    PeriodoAquisitivo,
    ProgramacaoFerias,
    db,
)


def _saldo(f, p):
    return st.saldo_periodo(f, p, date.today())


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
        saldo_snapshot=saldo,
        # Fechado já na data-retrato → regime snapshot: base = saldo_snapshot,
        # preservando o significado dos cenários (16/6/0…).
        snapshot_em=hoje,
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
    assert p_atual.saldo_snapshot == 16  # coluna intacta
    assert _saldo(f, p_atual) == 6       # 16 - 10 derivado da programação

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
    assert db.session.get(PeriodoAquisitivo, p.id).saldo_snapshot == 6  # inalterado
    assert ProgramacaoFerias.query.filter_by(funcionario_id=f.id).count() == 0


def test_aviso_previo_30_dias(app, client_gestor, gestor_comum):
    f, p = _setup_funcionario(saldo=16, setor_id=gestor_comum.setor_id)
    cedo = (date.today() + timedelta(days=5)).isoformat()

    r = client_gestor.post(
        f"/funcionarios/{f.id}/programar",
        data={"periodo_id": p.id, "data_inicio": cedo, "dias_gozo": 5},
        follow_redirects=True,
    )
    assert "antecedência" in r.get_data(as_text=True)
    assert db.session.get(PeriodoAquisitivo, p.id).saldo_snapshot == 16  # inalterado
    assert ProgramacaoFerias.query.filter_by(funcionario_id=f.id).count() == 0


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
    p_atual = db.session.get(PeriodoAquisitivo, p.id)
    assert p_atual.saldo_snapshot == 16  # coluna intacta
    assert _saldo(f, p_atual) == 6       # 16 - 10 derivado

    prog = ProgramacaoFerias.query.filter_by(funcionario_id=f.id).first()
    assert prog.criado_por_id == gestor_admin.id


def test_admin_programa_saldo_total_aparece_no_filtro_programada(
    app, client_admin
):
    f, p = _setup_funcionario(saldo=30)
    hoje = date.today().isoformat()

    r = client_admin.post(
        f"/funcionarios/{f.id}/programar",
        data={"periodo_id": p.id, "data_inicio": hoje, "dias_gozo": 30},
        follow_redirects=True,
    )
    assert "programadas com sucesso" in r.get_data(as_text=True)
    p_atual = db.session.get(PeriodoAquisitivo, p.id)
    assert p_atual.saldo_snapshot == 30  # coluna intacta
    assert _saldo(f, p_atual) == 0       # saldo todo programado

    html = client_admin.get("/funcionarios/?status=PROGRAMADA").get_data(as_text=True)
    assert f.nome in html


def test_admin_nao_programa_no_passado(app, client_admin, gestor_admin):
    f, p = _setup_funcionario(saldo=16)
    ontem = (date.today() - timedelta(days=1)).isoformat()

    r = client_admin.post(
        f"/funcionarios/{f.id}/programar",
        data={"periodo_id": p.id, "data_inicio": ontem, "dias_gozo": 5},
        follow_redirects=True,
    )
    assert "não pode estar no passado" in r.get_data(as_text=True)
    assert db.session.get(PeriodoAquisitivo, p.id).saldo_snapshot == 16  # inalterado
    assert ProgramacaoFerias.query.filter_by(funcionario_id=f.id).count() == 0


def test_form_admin_sem_aviso_minimo_hoje(app, client_admin, gestor_admin):
    # GET: admin vê a caixa informativa da isenção e prefill = hoje (dd/mm/aaaa).
    f, p = _setup_funcionario(saldo=16)

    r = client_admin.get(f"/funcionarios/{f.id}/programar")
    html = r.get_data(as_text=True)
    assert "sem exigência de aviso prévio" in html
    assert f'value="{date.today().strftime("%d/%m/%Y")}"' in html


def test_form_gestor_comum_minimo_30_dias(app, client_gestor, gestor_comum):
    # GET: gestor comum segue vendo o aviso de 30 dias e prefill = hoje + 30.
    f, p = _setup_funcionario(saldo=16, setor_id=gestor_comum.setor_id)

    r = client_gestor.get(f"/funcionarios/{f.id}/programar")
    html = r.get_data(as_text=True)
    assert "Aviso prévio de 30 dias" in html
    assert f'value="{(date.today() + timedelta(days=30)).strftime("%d/%m/%Y")}"' in html


def test_programar_aceita_data_brasileira(app, client_gestor, gestor_comum):
    # O campo de data aceita o formato brasileiro dd/mm/aaaa.
    f, p = _setup_funcionario(saldo=16, setor_id=gestor_comum.setor_id)
    inicio = (date.today() + timedelta(days=45)).strftime("%d/%m/%Y")

    r = client_gestor.post(
        f"/funcionarios/{f.id}/programar",
        data={"periodo_id": p.id, "data_inicio": inicio, "dias_gozo": 10},
        follow_redirects=True,
    )
    assert "programadas com sucesso" in r.get_data(as_text=True)
    p_atual = db.session.get(PeriodoAquisitivo, p.id)
    assert p_atual.saldo_snapshot == 16  # coluna intacta
    assert _saldo(f, p_atual) == 6


def test_programar_data_invalida_mensagem_pt(app, client_gestor, gestor_comum):
    f, p = _setup_funcionario(saldo=16, setor_id=gestor_comum.setor_id)

    r = client_gestor.post(
        f"/funcionarios/{f.id}/programar",
        data={"periodo_id": p.id, "data_inicio": "31/02/2026", "dias_gozo": 5},
        follow_redirects=True,
    )
    assert "use o formato dd/mm/aaaa" in r.get_data(as_text=True)
    assert db.session.get(PeriodoAquisitivo, p.id).saldo_snapshot == 16  # inalterado
    assert ProgramacaoFerias.query.filter_by(funcionario_id=f.id).count() == 0


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
    f, p = _setup_funcionario(saldo=16, setor_id=gestor_comum.setor_id)
    prog = _programacao(
        f, p, date.today() + timedelta(days=45), 10,
        criado_por_id=gestor_comum.id,
    )
    pid = prog.id
    assert _saldo(f, p) == 6  # 16 - 10 enquanto a programação existe

    r = client_gestor.post(
        f"/funcionarios/{f.id}/programacoes/{pid}/cancelar",
        follow_redirects=True,
    )
    assert "cancelada" in r.get_data(as_text=True)
    p_atual = db.session.get(PeriodoAquisitivo, p.id)
    assert p_atual.saldo_snapshot == 16  # coluna nunca mudou
    assert _saldo(f, p_atual) == 16      # apagar a linha devolveu o saldo
    assert db.session.get(ProgramacaoFerias, pid) is None


def test_cancelar_em_curso_sem_criador_restaura(app, client_gestor, gestor_comum):
    # Programação EM CURSO (começou há 9 dias) pode ser cancelada e o saldo
    # derivado volta inteiro — só a encerrada é intocável.
    f, p = _setup_funcionario(saldo=30, setor_id=gestor_comum.setor_id)
    prog = _programacao(
        f, p, date.today() - timedelta(days=9), 30, origem="import"
    )
    pid = prog.id
    assert _saldo(f, p) == 0

    r = client_gestor.post(
        f"/funcionarios/{f.id}/programacoes/{pid}/cancelar",
        follow_redirects=True,
    )
    assert "Saldo do período restaurado" in r.get_data(as_text=True)
    p_atual = db.session.get(PeriodoAquisitivo, p.id)
    assert p_atual.saldo_snapshot == 30
    assert _saldo(f, p_atual) == 30
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
    assert db.session.get(PeriodoAquisitivo, p.id).saldo_snapshot == 6


def test_cancelar_passada_proibido(app, client_gestor, gestor_comum):
    f, p = _setup_funcionario(saldo=16, setor_id=gestor_comum.setor_id)
    prog = _programacao(f, p, date.today() - timedelta(days=40), 10)  # fim no passado

    r = client_gestor.post(
        f"/funcionarios/{f.id}/programacoes/{prog.id}/cancelar",
        follow_redirects=True,
    )
    assert "já encerrada" in r.get_data(as_text=True)
    assert db.session.get(ProgramacaoFerias, prog.id) is not None
    assert _saldo(f, p) == 6  # os 10 gozados continuam descontados


def test_programar_contra_janela_virtual_materializa(app, client_admin):
    # Funcionário defasado: último período do banco fechou há ~400 dias e está
    # quitado → a janela seguinte (virtual, já fechada, saldo 30) aparece no
    # select e vira linha no banco só quando a programação é registrada.
    hoje = date.today()
    emp = Empresa(nome="Teste Ltda")
    db.session.add(emp)
    db.session.flush()
    f = Funcionario(empresa_id=emp.id, codigo="7", nome="DEFASADO DE TAL")
    db.session.add(f)
    db.session.flush()
    ultimo_fim = hoje - timedelta(days=400)
    db.session.add(PeriodoAquisitivo(
        funcionario_id=f.id,
        inicio=ultimo_fim - timedelta(days=364),
        fim=ultimo_fim,
        dias_direito=30,
        saldo_snapshot=0,          # quitado no retrato
        snapshot_em=hoje,
        limite_gozo=ultimo_fim + timedelta(days=365),
    ))
    db.session.commit()

    html = client_admin.get(f"/funcionarios/{f.id}/programar").get_data(as_text=True)
    assert "novo período" in html

    token = f"v:{(ultimo_fim + timedelta(days=1)).isoformat()}"
    r = client_admin.post(
        f"/funcionarios/{f.id}/programar",
        data={"periodo_id": token, "data_inicio": hoje.isoformat(), "dias_gozo": 10},
        follow_redirects=True,
    )
    assert "programadas com sucesso" in r.get_data(as_text=True)

    periodos = (
        PeriodoAquisitivo.query.filter_by(funcionario_id=f.id)
        .order_by(PeriodoAquisitivo.inicio)
        .all()
    )
    assert len(periodos) == 2
    novo = periodos[1]
    assert novo.inicio == ultimo_fim + timedelta(days=1)
    assert novo.snapshot_em is None       # regime 100% derivado
    assert novo.saldo_snapshot is None
    prog = ProgramacaoFerias.query.filter_by(funcionario_id=f.id).one()
    assert prog.periodo_aquisitivo_id == novo.id
    assert _saldo(f, novo) == 20          # 30 - 10

    # Repetir o token (double-submit / select desatualizado) cai na linha já
    # materializada — não duplica período.
    r = client_admin.post(
        f"/funcionarios/{f.id}/programar",
        data={
            "periodo_id": token,
            "data_inicio": (hoje + timedelta(days=40)).isoformat(),
            "dias_gozo": 5,
        },
        follow_redirects=True,
    )
    assert "programadas com sucesso" in r.get_data(as_text=True)
    assert PeriodoAquisitivo.query.filter_by(funcionario_id=f.id).count() == 2
    assert _saldo(f, novo) == 15


def test_programar_token_virtual_invalido(app, client_admin):
    f, p = _setup_funcionario(saldo=16)
    r = client_admin.post(
        f"/funcionarios/{f.id}/programar",
        data={
            "periodo_id": "v:2030-01-01",  # janela que não existe no servidor
            "data_inicio": date.today().isoformat(),
            "dias_gozo": 5,
        },
        follow_redirects=True,
    )
    assert "Período inválido" in r.get_data(as_text=True)
    assert ProgramacaoFerias.query.filter_by(funcionario_id=f.id).count() == 0


def test_periodo_fechado_pos_snapshot_permite_programar_30(app, client_admin):
    # Caso real do bug em prod: AG congelado em 27,5 (retrato anterior ao fim
    # do período) não pode limitar a programação — o direito integral é 30.
    hoje = date.today()
    emp = Empresa(nome="Teste Ltda")
    db.session.add(emp)
    db.session.flush()
    f = Funcionario(empresa_id=emp.id, codigo="9", nome="LUIS ANTONIO")
    db.session.add(f)
    db.session.flush()
    p = PeriodoAquisitivo(
        funcionario_id=f.id,
        inicio=hoje - timedelta(days=400),
        fim=hoje - timedelta(days=35),
        dias_direito=27.5,
        saldo_snapshot=27.5,
        snapshot_em=hoje - timedelta(days=60),  # retrato ANTES de fechar
        limite_gozo=hoje + timedelta(days=330),
    )
    db.session.add(p)
    db.session.commit()

    r = client_admin.post(
        f"/funcionarios/{f.id}/programar",
        data={"periodo_id": p.id, "data_inicio": hoje.isoformat(), "dias_gozo": 30},
        follow_redirects=True,
    )
    assert "programadas com sucesso" in r.get_data(as_text=True)
    p_atual = db.session.get(PeriodoAquisitivo, p.id)
    assert p_atual.saldo_snapshot == 27.5  # coluna intacta
    assert _saldo(f, p_atual) == 0         # 30 - 30


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
    assert db.session.get(PeriodoAquisitivo, p.id).saldo_snapshot == 6


def test_programacao_duplicada_na_mesma_data_e_rejeitada(app, client_admin):
    # A unique (funcionario, data_inicio) vira flash amigável, não 500.
    f, p = _setup_funcionario(saldo=30)
    hoje = date.today().isoformat()
    r = client_admin.post(
        f"/funcionarios/{f.id}/programar",
        data={"periodo_id": p.id, "data_inicio": hoje, "dias_gozo": 5},
        follow_redirects=True,
    )
    assert "programadas com sucesso" in r.get_data(as_text=True)

    r = client_admin.post(
        f"/funcionarios/{f.id}/programar",
        data={"periodo_id": p.id, "data_inicio": hoje, "dias_gozo": 5},
        follow_redirects=True,
    )
    assert "Não foi possível registrar" in r.get_data(as_text=True)
    assert ProgramacaoFerias.query.filter_by(funcionario_id=f.id).count() == 1


def test_integrityerror_nao_deixa_periodo_materializado_orfao(app, client_admin):
    # O rollback do commit precisa desfazer TAMBÉM o período recém-
    # materializado — senão fica período órfão no banco.
    hoje = date.today()
    emp = Empresa(nome="Teste Ltda")
    db.session.add(emp)
    db.session.flush()
    f = Funcionario(empresa_id=emp.id, codigo="8", nome="ORFAO DE TAL")
    db.session.add(f)
    db.session.flush()
    ultimo_fim = hoje - timedelta(days=400)
    db.session.add(PeriodoAquisitivo(
        funcionario_id=f.id,
        inicio=ultimo_fim - timedelta(days=364),
        fim=ultimo_fim,
        dias_direito=30,
        saldo_snapshot=0,
        snapshot_em=hoje,
        limite_gozo=ultimo_fim + timedelta(days=365),
    ))
    db.session.commit()
    conflito = hoje + timedelta(days=45)
    _programacao(f, None, conflito, 5)  # ocupa (funcionario, data_inicio)

    token = f"v:{(ultimo_fim + timedelta(days=1)).isoformat()}"
    r = client_admin.post(
        f"/funcionarios/{f.id}/programar",
        data={
            "periodo_id": token,
            "data_inicio": conflito.isoformat(),
            "dias_gozo": 5,
        },
        follow_redirects=True,
    )
    assert "Não foi possível registrar" in r.get_data(as_text=True)
    assert PeriodoAquisitivo.query.filter_by(funcionario_id=f.id).count() == 1
    assert ProgramacaoFerias.query.filter_by(funcionario_id=f.id).count() == 1
