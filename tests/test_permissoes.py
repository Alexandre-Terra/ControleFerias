"""Escopo por setor: não-admin só vê/gere o próprio setor; admin gere todos."""
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from app.models import (
    Empresa,
    Funcionario,
    Gestor,
    PeriodoAquisitivo,
    Setor,
    db,
)


def _empresa(nome="ACME"):
    e = Empresa(nome=nome)
    db.session.add(e)
    db.session.flush()
    return e


def _funcionario(empresa, setor_id, codigo, nome):
    f = Funcionario(
        empresa_id=empresa.id, setor_id=setor_id, codigo=codigo, nome=nome
    )
    db.session.add(f)
    db.session.flush()
    return f


def _periodo_elegivel(f, saldo=20):
    hoje = date.today()
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
    return p


def _periodo_a_vencer(f, saldo=20):
    """Período fechado com limite_gozo em ≤60 dias → status A_VENCER (entra no
    painel de risco)."""
    hoje = date.today()
    p = PeriodoAquisitivo(
        funcionario_id=f.id,
        inicio=hoje - timedelta(days=400),
        fim=hoje - timedelta(days=35),
        dias_direito=30,
        saldo_snapshot=saldo,
        snapshot_em=hoje,
        limite_gozo=hoje + timedelta(days=30),
    )
    db.session.add(p)
    db.session.commit()
    return p


# --- não-admin: bloqueios ---------------------------------------------------


def test_nao_admin_403_em_outro_setor(client_gestor, gestor_comum):
    outro = Setor(nome="Administrativo")
    db.session.add(outro)
    db.session.flush()
    emp = _empresa()
    f = _funcionario(emp, outro.id, "1", "BELTRANO")
    p = _periodo_elegivel(f)

    assert client_gestor.get(f"/funcionarios/{f.id}").status_code == 403
    assert client_gestor.get(f"/funcionarios/{f.id}/programar").status_code == 403


def test_nao_admin_403_em_funcionario_sem_setor(client_gestor):
    emp = _empresa()
    f = _funcionario(emp, None, "1", "SEM SETOR")
    db.session.commit()
    assert client_gestor.get(f"/funcionarios/{f.id}").status_code == 403


def test_nao_admin_lista_so_seu_setor(client_gestor, gestor_comum):
    outro = Setor(nome="Administrativo")
    db.session.add(outro)
    db.session.flush()
    emp = _empresa()
    _funcionario(emp, gestor_comum.setor_id, "1", "MEU FULANO")
    _funcionario(emp, outro.id, "2", "OUTRO BELTRANO")
    db.session.commit()

    html = client_gestor.get("/funcionarios/").get_data(as_text=True)
    assert "MEU FULANO" in html
    assert "OUTRO BELTRANO" not in html


def test_nao_admin_pode_seu_setor(client_gestor, gestor_comum):
    emp = _empresa()
    f = _funcionario(emp, gestor_comum.setor_id, "1", "MEU FULANO")
    _periodo_elegivel(f)
    assert client_gestor.get(f"/funcionarios/{f.id}").status_code == 200
    assert client_gestor.get(f"/funcionarios/{f.id}/programar").status_code == 200


def test_definir_setor_so_admin(client_gestor, gestor_comum):
    emp = _empresa()
    f = _funcionario(emp, gestor_comum.setor_id, "1", "MEU FULANO")
    db.session.commit()
    r = client_gestor.post(
        f"/funcionarios/{f.id}/setor", data={"setor_id": gestor_comum.setor_id}
    )
    assert r.status_code == 403


# --- não-admin sem setor: vê nada ------------------------------------------


def test_nao_admin_sem_setor_nao_ve_nada(app):
    g = Gestor(
        nome="Sem Setor",
        email="semsetor@teste.com",
        senha_hash=generate_password_hash("senha123"),
        is_admin=False,
        setor_id=None,
        ativo=True,
    )
    db.session.add(g)
    emp = _empresa()
    f = _funcionario(emp, None, "1", "ALGUEM")
    db.session.commit()

    c = app.test_client()
    c.post("/login", data={"email": "semsetor@teste.com", "senha": "senha123"})
    html = c.get("/funcionarios/").get_data(as_text=True)
    assert "ALGUEM" not in html
    assert c.get(f"/funcionarios/{f.id}").status_code == 403


# --- admin: vê e gere todos -------------------------------------------------


def test_admin_ve_e_programa_qualquer_setor(client_admin):
    setor_x = Setor(nome="Produção")
    db.session.add(setor_x)
    db.session.flush()
    emp = _empresa()
    f_setor = _funcionario(emp, setor_x.id, "1", "COM SETOR")
    f_sem = _funcionario(emp, None, "2", "SEM SETOR")
    _periodo_elegivel(f_setor)
    _periodo_elegivel(f_sem)

    assert client_admin.get(f"/funcionarios/{f_setor.id}").status_code == 200
    assert client_admin.get(f"/funcionarios/{f_sem.id}").status_code == 200
    assert client_admin.get(f"/funcionarios/{f_sem.id}/programar").status_code == 200


def test_admin_define_setor(client_admin):
    setor_x = Setor(nome="Produção")
    db.session.add(setor_x)
    db.session.flush()
    emp = _empresa()
    f = _funcionario(emp, None, "1", "SEM SETOR")
    db.session.commit()

    r = client_admin.post(
        f"/funcionarios/{f.id}/setor",
        data={"setor_id": setor_x.id},
        follow_redirects=True,
    )
    assert "Setor atualizado" in r.get_data(as_text=True)
    assert db.session.get(Funcionario, f.id).setor_id == setor_x.id


# --- dashboard (página de pouso) respeita o escopo --------------------------


def test_nao_admin_dashboard_so_seu_setor(client_gestor, gestor_comum):
    outro = Setor(nome="Administrativo")
    db.session.add(outro)
    db.session.flush()
    emp = _empresa()
    f_meu = _funcionario(emp, gestor_comum.setor_id, "1", "RISCO MEU")
    f_outro = _funcionario(emp, outro.id, "2", "RISCO OUTRO")
    _periodo_a_vencer(f_meu)
    _periodo_a_vencer(f_outro)

    html = client_gestor.get("/").get_data(as_text=True)
    assert "RISCO MEU" in html
    assert "RISCO OUTRO" not in html


def test_admin_dashboard_ve_todos(client_admin):
    s1 = Setor(nome="Produção")
    s2 = Setor(nome="Administrativo")
    db.session.add_all([s1, s2])
    db.session.flush()
    emp = _empresa()
    f1 = _funcionario(emp, s1.id, "1", "RISCO UM")
    f2 = _funcionario(emp, s2.id, "2", "RISCO DOIS")
    _periodo_a_vencer(f1)
    _periodo_a_vencer(f2)

    html = client_admin.get("/").get_data(as_text=True)
    assert "RISCO UM" in html
    assert "RISCO DOIS" in html
