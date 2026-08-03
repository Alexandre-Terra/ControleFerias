"""CRUD admin de funcionários: criar e inativar/reativar (soft-delete)."""
from datetime import date, timedelta

from app.models import (
    Empresa,
    Funcionario,
    PeriodoAquisitivo,
    ProgramacaoFerias,
    Setor,
    db,
)


def _empresa(nome="ACME"):
    e = Empresa(nome=nome)
    db.session.add(e)
    db.session.commit()
    return e


def _periodo_a_vencer(func_id):
    hoje = date.today()
    db.session.add(PeriodoAquisitivo(
        funcionario_id=func_id,
        inicio=hoje - timedelta(days=400),
        fim=hoje - timedelta(days=35),
        dias_direito=30,
        saldo_snapshot=20,
        snapshot_em=hoje,
        limite_gozo=hoje + timedelta(days=30),  # ≤60 → A_VENCER (entra no risco)
    ))
    db.session.commit()


def test_admin_cria_funcionario(client_admin, setor):
    emp = _empresa()
    r = client_admin.post(
        "/funcionarios/novo",
        data={
            "empresa_id": emp.id,
            "setor_id": setor.id,
            "codigo": "777",
            "nome": "NOVO COLABORADOR",
            "data_admissao": "2026-01-15",
        },
        follow_redirects=True,
    )
    assert "criado" in r.get_data(as_text=True)
    f = Funcionario.query.filter_by(codigo="777").first()
    assert f is not None
    assert f.ativo is True
    assert f.setor_id == setor.id
    assert f.empresa_id == emp.id


def test_cria_funcionario_codigo_duplicado(client_admin):
    emp = _empresa()
    db.session.add(Funcionario(empresa_id=emp.id, codigo="1", nome="EXISTENTE"))
    db.session.commit()
    r = client_admin.post(
        "/funcionarios/novo",
        data={"empresa_id": emp.id, "setor_id": 0, "codigo": "1", "nome": "OUTRO"},
        follow_redirects=True,
    )
    assert "Já existe funcionário" in r.get_data(as_text=True)


def test_nao_admin_nao_cria_funcionario(client_gestor):
    assert client_gestor.get("/funcionarios/novo").status_code == 403


def test_inativar_some_da_lista_e_dashboard(client_admin):
    s = Setor(nome="Operações")
    db.session.add(s)
    db.session.flush()
    emp = _empresa()
    f = Funcionario(empresa_id=emp.id, setor_id=s.id, codigo="9", nome="RISCO FULANO")
    db.session.add(f)
    db.session.flush()
    _periodo_a_vencer(f.id)

    # antes: aparece na lista e no painel
    assert "RISCO FULANO" in client_admin.get("/funcionarios/").get_data(as_text=True)
    assert "RISCO FULANO" in client_admin.get("/").get_data(as_text=True)

    r = client_admin.post(f"/funcionarios/{f.id}/inativar", follow_redirects=True)
    assert "inativado" in r.get_data(as_text=True)

    # depois: some das DUAS telas
    assert "RISCO FULANO" not in client_admin.get("/funcionarios/").get_data(as_text=True)
    assert "RISCO FULANO" not in client_admin.get("/").get_data(as_text=True)
    # mas aparece na visão de inativos
    assert "RISCO FULANO" in client_admin.get(
        "/funcionarios/?inativos=1"
    ).get_data(as_text=True)

    # reativa → reaparece
    client_admin.post(f"/funcionarios/{f.id}/reativar", follow_redirects=True)
    assert "RISCO FULANO" in client_admin.get("/funcionarios/").get_data(as_text=True)


def test_nao_admin_nao_inativa(client_gestor, gestor_comum):
    emp = _empresa()
    f = Funcionario(
        empresa_id=emp.id, setor_id=gestor_comum.setor_id, codigo="3", nome="MEU"
    )
    db.session.add(f)
    db.session.commit()
    assert client_gestor.post(f"/funcionarios/{f.id}/inativar").status_code == 403


def test_programar_bloqueado_para_inativo(client_admin):
    emp = _empresa()
    f = Funcionario(empresa_id=emp.id, codigo="5", nome="INATIVO", ativo=False)
    db.session.add(f)
    db.session.flush()
    hoje = date.today()
    db.session.add(PeriodoAquisitivo(
        funcionario_id=f.id,
        inicio=hoje - timedelta(days=400),
        fim=hoje - timedelta(days=35),
        dias_direito=30,
        saldo_snapshot=20,
        snapshot_em=hoje,
        limite_gozo=hoje + timedelta(days=200),
    ))
    db.session.commit()
    r = client_admin.get(f"/funcionarios/{f.id}/programar", follow_redirects=True)
    assert "inativo" in r.get_data(as_text=True).lower()


def _funcionario_com_periodo(saldo=30, codigo="55", nome="PARCIAL DE TAL"):
    hoje = date.today()
    emp = _empresa(nome=f"EMP {codigo}")
    f = Funcionario(empresa_id=emp.id, codigo=codigo, nome=nome)
    db.session.add(f)
    db.session.flush()
    p = PeriodoAquisitivo(
        funcionario_id=f.id,
        inicio=hoje - timedelta(days=400),
        fim=hoje - timedelta(days=35),
        dias_direito=30,
        saldo_snapshot=saldo,
        snapshot_em=hoje,
        limite_gozo=hoje + timedelta(days=200),
    )
    db.session.add(p)
    db.session.commit()
    return f, p


def _programa(f, p, inicio, dias):
    db.session.add(ProgramacaoFerias(
        funcionario_id=f.id,
        periodo_aquisitivo_id=p.id,
        data_inicio=inicio,
        dias_gozo=dias,
        data_fim=inicio + timedelta(days=dias - 1),
        origem="manual",
    ))
    db.session.commit()


def test_lista_mostra_residuo_de_programacao_parcial(client_admin):
    # Programação parcial: badge PROGRAMADA, mas os 20 dias que sobram
    # continuam na coluna "Dias disp." (antes sumiam como "—").
    hoje = date.today()
    f, p = _funcionario_com_periodo(saldo=30)
    _programa(f, p, hoje + timedelta(days=40), 10)

    html = client_admin.get("/funcionarios/").get_data(as_text=True)
    assert "Programada" in html
    assert ">20<" in html


def test_lista_mostra_zero_para_quitado(client_admin):
    # Período todo gozado: 0 explícito (e não "—", que significa "sem período
    # fechado").
    hoje = date.today()
    f, p = _funcionario_com_periodo(saldo=30, codigo="56", nome="QUITADO DE TAL")
    _programa(f, p, hoje - timedelta(days=60), 30)  # encerrada

    html = client_admin.get("/funcionarios/").get_data(as_text=True)
    assert ">0<" in html


def test_detalhe_mostra_direito_integral_e_janela_prevista(client_admin):
    # Caso do bug: AG congelado em 27,5 → detalhe mostra Direito/Restantes 30;
    # e a janela aquisitiva seguinte aparece como "previsto".
    hoje = date.today()
    emp = _empresa(nome="EMP 57")
    f = Funcionario(empresa_id=emp.id, codigo="57", nome="CONGELADO DE TAL")
    db.session.add(f)
    db.session.flush()
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

    html = client_admin.get(f"/funcionarios/{f.id}").get_data(as_text=True)
    assert ">30<" in html          # direito/saldo integrais, não 27,5
    assert "27.5" not in html and "27,5" not in html
    assert "previsto" in html      # janela virtual seguinte
