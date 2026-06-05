"""CRUD admin de setores, com bloqueio de exclusão quando em uso."""
from app.models import Empresa, Funcionario, Setor, db


def test_admin_cria_setor(client_admin):
    r = client_admin.post(
        "/setores/novo", data={"nome": "Logística"}, follow_redirects=True
    )
    assert "criado" in r.get_data(as_text=True)
    assert Setor.query.filter_by(nome="Logística").first() is not None


def test_cria_setor_duplicado(client_admin):
    db.session.add(Setor(nome="RH"))
    db.session.commit()
    r = client_admin.post("/setores/novo", data={"nome": "RH"}, follow_redirects=True)
    assert "Já existe" in r.get_data(as_text=True)


def test_renomeia_setor(client_admin):
    s = Setor(nome="Velho")
    db.session.add(s)
    db.session.commit()
    r = client_admin.post(
        f"/setores/{s.id}/renomear", data={"nome": "Novo"}, follow_redirects=True
    )
    assert "renomeado" in r.get_data(as_text=True)
    assert db.session.get(Setor, s.id).nome == "Novo"


def test_exclui_setor_vazio(client_admin):
    s = Setor(nome="Temporário")
    db.session.add(s)
    db.session.commit()
    sid = s.id
    r = client_admin.post(f"/setores/{sid}/excluir", follow_redirects=True)
    assert "excluído" in r.get_data(as_text=True)
    assert db.session.get(Setor, sid) is None


def test_nao_exclui_setor_em_uso_por_inativo(client_admin):
    """O único vínculo é um funcionário INATIVO — ainda assim deve bloquear
    (um inativo continua referenciando a FK)."""
    s = Setor(nome="Em Uso")
    db.session.add(s)
    db.session.flush()
    emp = Empresa(nome="ACME")
    db.session.add(emp)
    db.session.flush()
    db.session.add(Funcionario(
        empresa_id=emp.id, setor_id=s.id, codigo="1", nome="X", ativo=False
    ))
    db.session.commit()

    r = client_admin.post(f"/setores/{s.id}/excluir", follow_redirects=True)
    assert "em uso" in r.get_data(as_text=True).lower()
    assert db.session.get(Setor, s.id) is not None


def test_nao_exclui_setor_em_uso_por_gestor(client_admin, gestor_comum):
    """gestor_comum já tem um setor (fixture) — excluí-lo deve bloquear."""
    sid = gestor_comum.setor_id
    r = client_admin.post(f"/setores/{sid}/excluir", follow_redirects=True)
    assert "em uso" in r.get_data(as_text=True).lower()
    assert db.session.get(Setor, sid) is not None


def test_nao_admin_403_setores(client_gestor):
    assert client_gestor.get("/setores/").status_code == 403
    assert client_gestor.post("/setores/novo", data={"nome": "X"}).status_code == 403
