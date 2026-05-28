"""Modelos do banco de dados.

Importante: o STATUS de férias nunca é armazenado — é derivado em runtime
(ver app/status.py), porque depende da data de hoje.
"""
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def _agora():
    return datetime.now(timezone.utc)


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

    funcionario = db.relationship("Funcionario", back_populates="programacoes")
    periodo = db.relationship("PeriodoAquisitivo")
