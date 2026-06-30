"""Modelos do banco de dados.

Importante: o STATUS de férias nunca é armazenado — é derivado em runtime
(ver app/status.py), porque depende da data de hoje.
"""
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError

db = SQLAlchemy()


def _agora():
    return datetime.now(timezone.utc)


class Gestor(db.Model):
    __tablename__ = "gestor"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    # Escopo de acesso: gestor não-admin só gere funcionários do seu setor.
    # Admin ignora isto (vê/gere todos). Setor é global (cross-empresa).
    setor_id = db.Column(db.Integer, db.ForeignKey("setor.id"), nullable=True)
    criado_em = db.Column(db.DateTime, default=_agora)

    setor = db.relationship("Setor", back_populates="gestores")

    def pode_gerir(self, funcionario):
        """Admin gere todos; gestor de setor só gere o próprio setor.

        Mesma regra que ``auth.filtrar_por_escopo`` aplica no nível de query —
        manter as duas em sincronia.
        """
        if self.is_admin:
            return True
        return self.setor_id is not None and funcionario.setor_id == self.setor_id


class Empresa(db.Model):
    __tablename__ = "empresa"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), unique=True, nullable=False)
    cnpj = db.Column(db.String(20), nullable=True)

    funcionarios = db.relationship(
        "Funcionario", back_populates="empresa", cascade="all, delete-orphan"
    )


class Setor(db.Model):
    __tablename__ = "setor"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), unique=True, nullable=False)

    funcionarios = db.relationship("Funcionario", back_populates="setor")
    gestores = db.relationship("Gestor", back_populates="setor")


class Funcionario(db.Model):
    __tablename__ = "funcionario"
    __table_args__ = (
        db.UniqueConstraint("empresa_id", "codigo", name="uq_func_empresa_codigo"),
    )

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresa.id"), nullable=False)
    setor_id = db.Column(db.Integer, db.ForeignKey("setor.id"), nullable=True)

    codigo = db.Column(db.String(40), nullable=False)
    nome = db.Column(db.String(160), nullable=False)
    data_admissao = db.Column(db.Date, nullable=True)
    vencto_ferias = db.Column(db.Date, nullable=True)
    # Soft-delete: funcionário inativo some das listas/painel (admin reativa).
    ativo = db.Column(db.Boolean, nullable=False, default=True)

    empresa = db.relationship("Empresa", back_populates="funcionarios")
    setor = db.relationship("Setor", back_populates="funcionarios")
    periodos = db.relationship(
        "PeriodoAquisitivo",
        back_populates="funcionario",
        cascade="all, delete-orphan",
        order_by="PeriodoAquisitivo.inicio",
    )
    programacoes = db.relationship(
        "ProgramacaoFerias",
        back_populates="funcionario",
        cascade="all, delete-orphan",
        order_by="ProgramacaoFerias.data_inicio",
    )


class PeriodoAquisitivo(db.Model):
    __tablename__ = "periodo_aquisitivo"
    __table_args__ = (
        db.UniqueConstraint("funcionario_id", "inicio", name="uq_periodo_func_inicio"),
    )

    id = db.Column(db.Integer, primary_key=True)
    funcionario_id = db.Column(
        db.Integer, db.ForeignKey("funcionario.id"), nullable=False
    )

    inicio = db.Column(db.Date, nullable=False)          # Q - início aquisitivo
    fim = db.Column(db.Date, nullable=True)              # R - fim aquisitivo
    dias_direito = db.Column(db.Float, nullable=True)    # AC
    dias_restantes = db.Column(db.Float, nullable=True)  # AG
    limite_gozo = db.Column(db.Date, nullable=True)      # AH - fim do concessivo
    dias_abono = db.Column(db.Float, nullable=True)      # Z  (preservado)
    decimo_terceiro = db.Column(db.String(40), nullable=True)  # AB (preservado)

    funcionario = db.relationship("Funcionario", back_populates="periodos")


class ProgramacaoFerias(db.Model):
    __tablename__ = "programacao_ferias"
    __table_args__ = (
        db.UniqueConstraint(
            "funcionario_id", "data_inicio", name="uq_prog_func_inicio"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    funcionario_id = db.Column(
        db.Integer, db.ForeignKey("funcionario.id"), nullable=False
    )
    periodo_aquisitivo_id = db.Column(
        db.Integer, db.ForeignKey("periodo_aquisitivo.id"), nullable=True
    )

    data_inicio = db.Column(db.Date, nullable=False)     # W
    dias_gozo = db.Column(db.Integer, nullable=False)    # X
    data_fim = db.Column(db.Date, nullable=True)         # derivado
    origem = db.Column(db.String(10), nullable=False, default="manual")  # import|manual
    criado_em = db.Column(db.DateTime, default=_agora)
    criado_por_id = db.Column(
        db.Integer, db.ForeignKey("gestor.id"), nullable=True
    )

    funcionario = db.relationship("Funcionario", back_populates="programacoes")
    periodo = db.relationship("PeriodoAquisitivo")
    criado_por = db.relationship("Gestor")


# --- Integração WhatsApp (Z-API) -------------------------------------------
# Aviso ativo de férias por WhatsApp, todo configurável pelo admin (não por env
# var). A configuração é um singleton (uma linha, id=1); ``EnvioZapi`` é o log de
# disparos (histórico + trava anti-duplicação). O STATUS de férias continua NUNCA
# persistido — ``EnvioZapi`` só registra o evento de entrega e a contagem do
# instante do envio, não o status autoritativo (esse vem sempre de status.py).

# Textos-modelo padrão (o admin edita pela tela). Variáveis no formato {chave}
# são substituídas em runtime (render seguro: chaves desconhecidas ficam intactas).
_MODELO_CABECALHO = (
    "🏖️ *Controle de Férias* — {data}\n\n"
    "{total} colaborador(es) com pendência de férias:\n"
)
_MODELO_LINHA = "• *{nome}* ({empresa}) — {status}, saldo {dias}, limite {limite}"
_MODELO_SEM_PENDENCIAS = (
    "✅ *Controle de Férias* — {data}\nNenhuma pendência de férias hoje."
)
# Bloco de "tempo de serviço": marcos por data de admissão (45/90/120 dias e
# aniversários). Ver app/tempo.py. {dias} é quantos dias faltam para o marco.
_MODELO_TEMPO_CABECALHO = (
    "⏳ *Tempo de empresa* — {data}\n\n"
    "{total} colaborador(es) com marco de tempo de serviço:\n"
)
_MODELO_TEMPO = "• *{nome}* ({empresa}) — {marco} em {data} (faltam {dias} dia(s))"


class ConfiguracaoZapi(db.Model):
    """Configuração única (singleton, id=1) da integração Z-API.

    Use sempre ``ConfiguracaoZapi.obter()`` para ler/criar — garante a linha
    única mesmo sob corrida entre workers do gunicorn.
    """

    __tablename__ = "configuracao_zapi"

    id = db.Column(db.Integer, primary_key=True)
    ativo = db.Column(db.Boolean, nullable=False, default=False)

    # Credenciais Z-API. instance_token vai no PATH da URL; client_token no
    # header Client-Token — nunca logar a URL completa nem o header (ver zapi.py).
    base_url = db.Column(db.String(200), nullable=False, default="https://api.z-api.io")
    instance_id = db.Column(db.String(120), nullable=True)
    instance_token = db.Column(db.String(200), nullable=True)
    client_token = db.Column(db.String(200), nullable=True)

    # Números de destino (avulsos), um por linha. Recebem o resumo geral.
    destinatarios = db.Column(db.Text, nullable=True)

    # Regras: quais status entram no resumo.
    notificar_vencida = db.Column(db.Boolean, nullable=False, default=True)
    notificar_a_vencer = db.Column(db.Boolean, nullable=False, default=True)
    notificar_tem_direito = db.Column(db.Boolean, nullable=False, default=False)
    # Inclui no resumo os marcos de tempo de serviço (45/90/120 dias e
    # aniversários) cujo dia de aviso é hoje. Independente das regras de férias.
    notificar_tempo_servico = db.Column(db.Boolean, nullable=False, default=True)
    # Limiar (em dias) da faixa "a vencer" usado SÓ na notificação — independente
    # do ALERTA_A_VENCER_DIAS do painel. Default espelha o padrão do app (60).
    antecedencia_dias = db.Column(db.Integer, nullable=False, default=60)
    # Janela de disparo do envio agendado (hora local; depende de TZ no cron).
    hora_envio = db.Column(db.Integer, nullable=False, default=8)
    apenas_dias_uteis = db.Column(db.Boolean, nullable=False, default=True)
    # Se False, dias sem pendência não geram envio (e não gravam log "ok").
    enviar_se_vazio = db.Column(db.Boolean, nullable=False, default=False)

    # Modelos de mensagem (editáveis). Ver _MODELO_* para as variáveis.
    modelo_cabecalho = db.Column(db.Text, nullable=False, default=_MODELO_CABECALHO)
    modelo_linha = db.Column(db.Text, nullable=False, default=_MODELO_LINHA)
    modelo_sem_pendencias = db.Column(
        db.Text, nullable=False, default=_MODELO_SEM_PENDENCIAS
    )
    modelo_tempo_cabecalho = db.Column(
        db.Text, nullable=False, default=_MODELO_TEMPO_CABECALHO
    )
    modelo_tempo = db.Column(db.Text, nullable=False, default=_MODELO_TEMPO)

    atualizado_em = db.Column(db.DateTime, default=_agora, onupdate=_agora)
    atualizado_por_id = db.Column(
        db.Integer, db.ForeignKey("gestor.id"), nullable=True
    )

    atualizado_por = db.relationship("Gestor")

    @classmethod
    def obter(cls):
        """Retorna o singleton, criando-o (id=1) com os defaults se não existir.

        Robusto a corrida: se dois processos criarem ao mesmo tempo, o segundo
        cai no ``IntegrityError`` e relê a linha já gravada.
        """
        cfg = db.session.get(cls, 1)
        if cfg is not None:
            return cfg
        cfg = cls(id=1)
        db.session.add(cfg)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            cfg = db.session.get(cls, 1)
        return cfg

    def lista_destinatarios(self):
        """Linhas cruas de destinatários (uma por linha), como o admin digitou."""
        if not self.destinatarios:
            return []
        return [ln.strip() for ln in self.destinatarios.splitlines() if ln.strip()]

    def destinatarios_validos(self):
        """Telefones normalizados, deduplicados e válidos (descarta o resto).

        É a lista usada de fato para enviar e para a trava anti-duplicação:
        evita disparo dobrado (mesmo número repetido, ou em formatos diferentes
        que normalizam para o mesmo) e impede que uma linha inválida seja
        re-tentada a cada execução do cron.
        """
        from .zapi import normalizar_telefone

        validos = []
        for linha in self.lista_destinatarios():
            numero = normalizar_telefone(linha)
            if numero and numero not in validos:
                validos.append(numero)
        return validos

    def credenciais_ok(self):
        return bool(self.base_url and self.instance_id and self.instance_token)

    def pronta(self):
        """Apta a enviar: ativa, com credenciais e ao menos um destinatário válido."""
        return bool(
            self.ativo and self.credenciais_ok() and self.destinatarios_validos()
        )


class EnvioZapi(db.Model):
    """Log de cada disparo (por destinatário) — histórico no HUD e anti-dup."""

    __tablename__ = "envio_zapi"

    id = db.Column(db.Integer, primary_key=True)
    criado_em = db.Column(db.DateTime, default=_agora)
    # Dia de referência (data local) do resumo — base da trava anti-duplicação.
    data_referencia = db.Column(db.Date, nullable=False)
    tipo = db.Column(db.String(10), nullable=False, default="agendado")  # agendado|teste
    destinatario = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(10), nullable=False)  # ok|erro
    detalhe = db.Column(db.Text, nullable=True)  # saneado — nunca contém token
    total_itens = db.Column(db.Integer, nullable=True)
