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
    is_admin = BooleanField("Administrador")
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
