"""Formulários (Flask-WTF) — CSRF e validação básica.

As validações que dependem do banco (aviso de 30 dias, saldo do período)
são feitas na rota, pois precisam do período escolhido e da data de hoje.
"""
from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    NumberRange,
    Optional,
)


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    senha = PasswordField("Senha", validators=[DataRequired()])
    submit = SubmitField("Entrar")


class ProgramacaoForm(FlaskForm):
    periodo_id = SelectField("Período aquisitivo", coerce=int,
                             validators=[DataRequired()])
    data_inicio = DateField("Início das férias", validators=[DataRequired()])
    dias_gozo = IntegerField(
        "Dias de gozo", validators=[DataRequired(), NumberRange(min=1, max=30)]
    )
    submit = SubmitField("Programar férias")


class GestorForm(FlaskForm):
    """Criação/edição de gestor pelo admin.

    Na edição, ``senha`` pode ficar em branco (não altera).
    """
    nome = StringField("Nome", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=160)])
    senha = PasswordField("Senha", validators=[Optional(), Length(min=6)])
    # 0 = "— Nenhum"; choices preenchidas na rota. Não-admin exige setor
    # (validado na rota, junto das demais checagens de email/senha).
    setor_id = SelectField("Setor", coerce=int, validators=[Optional()])
    is_admin = BooleanField("Administrador")
    submit = SubmitField("Salvar")


class SetorForm(FlaskForm):
    """Criação/renomeação de setor pelo admin."""
    nome = StringField("Nome", validators=[DataRequired(), Length(max=80)])
    submit = SubmitField("Salvar")


class FuncionarioForm(FlaskForm):
    """Cadastro manual de funcionário pelo admin (novos colaboradores).

    Períodos aquisitivos continuam vindo do importer — não há entrada manual.
    """
    empresa_id = SelectField("Empresa", coerce=int, validators=[DataRequired()])
    # 0 = "— Não definido"; choices preenchidas na rota.
    setor_id = SelectField("Setor", coerce=int, validators=[Optional()])
    codigo = StringField("Código", validators=[DataRequired(), Length(max=40)])
    nome = StringField("Nome", validators=[DataRequired(), Length(max=160)])
    data_admissao = DateField("Admissão", validators=[Optional()])
    submit = SubmitField("Salvar")


class MudarSenhaForm(FlaskForm):
    """Reset de senha pelo admin."""
    senha = PasswordField(
        "Nova senha", validators=[DataRequired(), Length(min=6)]
    )
    confirmar = PasswordField(
        "Confirmar senha",
        validators=[DataRequired(), EqualTo("senha", message="As senhas não conferem.")],
    )
    submit = SubmitField("Alterar senha")


class AlterarSenhaForm(FlaskForm):
    """Self-service: gestor troca a própria senha (exige a senha atual).

    A senha atual não vira validator — é conferida na rota com
    ``check_password_hash`` (precisa do hash do gestor logado).
    """
    senha_atual = PasswordField("Senha atual", validators=[DataRequired()])
    senha = PasswordField(
        "Nova senha", validators=[DataRequired(), Length(min=6)]
    )
    confirmar = PasswordField(
        "Confirmar nova senha",
        validators=[DataRequired(), EqualTo("senha", message="As senhas não conferem.")],
    )
    submit = SubmitField("Alterar senha")
