"""Testes do CRUD admin de gestores."""
from app.models import Gestor, db


def test_listar_so_para_admin(client_admin):
    r = client_admin.get("/gestores/")
    assert r.status_code == 200
    assert "Admin Teste" in r.get_data(as_text=True)


def test_criar_gestor(client_admin, setor):
    r = client_admin.post(
        "/gestores/novo",
        data={
            "nome": "Novo Gestor",
            "email": "novo@teste.com",
            "senha": "senha123",
            "setor_id": setor.id,
            # is_admin omitido → False
        },
        follow_redirects=True,
    )
    assert "Gestor Novo Gestor criado" in r.get_data(as_text=True)
    g = Gestor.query.filter_by(email="novo@teste.com").first()
    assert g is not None
    assert g.is_admin is False
    assert g.setor_id == setor.id
    assert g.ativo is True


def test_criar_gestor_admin_dispensa_setor(client_admin):
    r = client_admin.post(
        "/gestores/novo",
        data={
            "nome": "Outro Admin",
            "email": "admin2@teste.com",
            "senha": "senha123",
            "setor_id": 0,
            "is_admin": "y",
        },
        follow_redirects=True,
    )
    assert "criado" in r.get_data(as_text=True)
    g = Gestor.query.filter_by(email="admin2@teste.com").first()
    assert g is not None and g.is_admin is True and g.setor_id is None


def test_criar_gestor_nao_admin_sem_setor_falha(client_admin):
    r = client_admin.post(
        "/gestores/novo",
        data={
            "nome": "Sem Setor",
            "email": "semsetor@teste.com",
            "senha": "senha123",
            "setor_id": 0,
        },
        follow_redirects=True,
    )
    assert "precisa de um setor" in r.get_data(as_text=True)
    assert Gestor.query.filter_by(email="semsetor@teste.com").first() is None


def test_criar_gestor_email_duplicado(client_admin, gestor_admin):
    r = client_admin.post(
        "/gestores/novo",
        data={
            "nome": "Outro",
            "email": gestor_admin.email,
            "senha": "senha123",
            "setor_id": 0,
        },
        follow_redirects=True,
    )
    assert "Já existe" in r.get_data(as_text=True)


def test_editar_gestor_muda_setor(client_admin, gestor_comum):
    from app.models import Setor

    outro = Setor(nome="Administrativo")
    db.session.add(outro)
    db.session.commit()
    r = client_admin.post(
        f"/gestores/{gestor_comum.id}/editar",
        data={
            "nome": gestor_comum.nome,
            "email": gestor_comum.email,
            "senha": "",  # mantém
            "setor_id": outro.id,
        },
        follow_redirects=True,
    )
    assert "atualizado" in r.get_data(as_text=True)
    assert db.session.get(Gestor, gestor_comum.id).setor_id == outro.id


def test_desativar_gestor(client_admin, gestor_comum):
    r = client_admin.post(
        f"/gestores/{gestor_comum.id}/desativar", follow_redirects=True
    )
    assert "desativado" in r.get_data(as_text=True)
    assert db.session.get(Gestor, gestor_comum.id).ativo is False


def test_admin_nao_pode_desativar_a_si_mesmo(client_admin, gestor_admin):
    r = client_admin.post(
        f"/gestores/{gestor_admin.id}/desativar", follow_redirects=True
    )
    assert "não pode desativar a si mesmo" in r.get_data(as_text=True)
    assert db.session.get(Gestor, gestor_admin.id).ativo is True


def test_reativar_gestor(client_admin, gestor_comum):
    gestor_comum.ativo = False
    db.session.commit()
    r = client_admin.post(
        f"/gestores/{gestor_comum.id}/reativar", follow_redirects=True
    )
    assert "reativado" in r.get_data(as_text=True)
    assert db.session.get(Gestor, gestor_comum.id).ativo is True


def test_mudar_senha(client_admin, gestor_comum):
    r = client_admin.post(
        f"/gestores/{gestor_comum.id}/senha",
        data={"senha": "novasenha", "confirmar": "novasenha"},
        follow_redirects=True,
    )
    assert "alterada" in r.get_data(as_text=True)
    # senha nova deve funcionar para login
    c = client_admin.application.test_client()
    r2 = c.post(
        "/login",
        data={"email": gestor_comum.email, "senha": "novasenha"},
        follow_redirects=False,
    )
    assert r2.status_code == 302


def test_gestor_comum_nao_acessa_admin(client_gestor):
    assert client_gestor.get("/gestores/").status_code == 403
    assert client_gestor.get("/gestores/novo").status_code == 403
