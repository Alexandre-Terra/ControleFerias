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
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    InputRequired,
    Length,
    NumberRange,
    Optional,
)
from wtforms.widgets import TextInput


class CampoDataBR(DateField):
    """Data no formato brasileiro (dd/mm/aaaa), exibida e digitada assim.

    Renderiza como texto (com máscara em ``app.js``) em vez do ``type=date``
    nativo, cujo formato de exibição segue o locale do navegador — não o do
    app. No parse aceita também ISO (aaaa-mm-dd) por compatibilidade.
    """

    widget = TextInput()

    def __init__(self, label=None, validators=None, **kwargs):
        kwargs.setdefault("format", ["%d/%m/%Y", "%Y-%m-%d"])
        super().__init__(label, validators, **kwargs)

    def process_formdata(self, valuelist):
        try:
            super().process_formdata(valuelist)
        except ValueError:
            raise ValueError("Data inválida — use o formato dd/mm/aaaa.")


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    senha = PasswordField("Senha", validators=[DataRequired()])
    submit = SubmitField("Entrar")


class ProgramacaoForm(FlaskForm):
    # coerce=str: o value é o id do período OU o token "v:<início ISO>" de uma
    # janela virtual ainda sem linha no banco. validate_choice=False porque a
    # janela pode ter sido materializada entre o GET e o POST (o value muda de
    # token para id) — quem valida é _resolver_periodo, no servidor.
    periodo_id = SelectField("Período aquisitivo", coerce=str,
                             validate_choice=False,
                             validators=[DataRequired()])
    # InputRequired (não DataRequired): DataRequired apagaria o erro de parse
    # do CampoDataBR quando a data é inválida e o substituiria pela mensagem
    # genérica em inglês.
    data_inicio = CampoDataBR(
        "Início das férias",
        validators=[InputRequired("Informe a data de início.")],
    )
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
    data_admissao = CampoDataBR("Admissão", validators=[Optional()])
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


class ConfiguracaoZapiForm(FlaskForm):
    """Configuração da integração WhatsApp (Z-API), editada pelo admin.

    Os tokens são ``PasswordField`` — o WTForms não re-renderiza o valor salvo
    (masking), e em branco mantêm o atual (mesmo padrão da senha em ``GestorForm``).
    """

    ativo = BooleanField("Integração ativa")

    base_url = StringField("URL base", validators=[Optional(), Length(max=200)])
    instance_id = StringField("Instance ID", validators=[Optional(), Length(max=120)])
    instance_token = PasswordField(
        "Instance Token", validators=[Optional(), Length(max=200)]
    )
    client_token = PasswordField(
        "Client-Token (Account Security Token)",
        validators=[Optional(), Length(max=200)],
    )
    destinatarios = TextAreaField("Destinatários", validators=[Optional()])

    notificar_vencida = BooleanField("Incluir férias vencidas")
    notificar_a_vencer = BooleanField("Incluir férias a vencer")
    notificar_tem_direito = BooleanField("Incluir quem já tem direito")
    notificar_tempo_servico = BooleanField("Incluir marcos de tempo de serviço")
    antecedencia_dias = IntegerField(
        "Antecedência (dias) para 'a vencer'",
        validators=[InputRequired(), NumberRange(min=0, max=3650)],
    )
    hora_envio = IntegerField(
        "Hora do envio (0–23)", validators=[InputRequired(), NumberRange(min=0, max=23)]
    )
    apenas_dias_uteis = BooleanField("Enviar apenas em dias úteis")
    enviar_se_vazio = BooleanField("Enviar mesmo sem pendências")

    modelo_cabecalho = TextAreaField("Modelo — cabeçalho", validators=[Optional()])
    modelo_linha = TextAreaField("Modelo — linha", validators=[Optional()])
    modelo_sem_pendencias = TextAreaField(
        "Modelo — sem pendências", validators=[Optional()]
    )
    modelo_tempo_cabecalho = TextAreaField(
        "Modelo — cabeçalho do tempo de serviço", validators=[Optional()]
    )
    modelo_tempo = TextAreaField(
        "Modelo — linha do tempo de serviço", validators=[Optional()]
    )

    submit = SubmitField("Salvar configuração")


class TestarEnvioZapiForm(FlaskForm):
    """Form mínimo só para o botão 'enviar teste' (carrega o token CSRF)."""

    submit = SubmitField("Enviar teste agora")


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
