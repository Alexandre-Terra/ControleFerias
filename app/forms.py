"""Formulários (Flask-WTF) — CSRF e validação básica.

As validações que dependem do banco (aviso de 30 dias, saldo do período)
são feitas na rota, pois precisam do período escolhido e da data de hoje.
"""
from flask_wtf import FlaskForm
from wtforms import DateField, IntegerField, PasswordField, SelectField, SubmitField
from wtforms.validators import DataRequired, NumberRange


class LoginForm(FlaskForm):
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
