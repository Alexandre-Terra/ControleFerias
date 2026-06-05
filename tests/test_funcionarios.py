"""CRUD admin de funcionários: criar e inativar/reativar (soft-delete)."""
from datetime import date, timedelta

from app.models import Empresa, Funcionario, PeriodoAquisitivo, Setor, db


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
        dias_restantes=20,
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
        dias_restantes=20,
        limite_gozo=hoje + timedelta(days=200),
    ))
    db.session.commit()
    r = client_admin.get(f"/funcionarios/{f.id}/programar", follow_redirects=True)
    assert "inativo" in r.get_data(as_text=True).lower()
