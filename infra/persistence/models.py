from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    JSON,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infra.persistence.db import Base


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("users.id"), primary_key=True),
    Column("role_id", ForeignKey("roles.id"), primary_key=True),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id"), primary_key=True),
)


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_dev: Mapped[bool] = mapped_column(Boolean, default=False)
    avatar_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    identidade: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    posto_graduacao: Mapped[str | None] = mapped_column(String(80), nullable=True)
    nome_guerra: Mapped[str | None] = mapped_column(String(120), nullable=True)
    telefone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    contato: Mapped[str | None] = mapped_column(String(120), nullable=True)
    divisao: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    secao: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

    roles: Mapped[list["RoleModel"]] = relationship(
        secondary=user_roles,
        back_populates="users",
    )


class CredentialAuditModel(Base):
    __tablename__ = "credential_audit"
    __table_args__ = (
        Index("ix_credential_audit_user_event", "user_id", "event_type"),
        Index("ix_credential_audit_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    encrypted_payload: Mapped[str] = mapped_column(Text)
    payload_sha256: Mapped[str] = mapped_column(String(128), index=True)
    crypto_version: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)


class RoleModel(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)

    users: Mapped[list[UserModel]] = relationship(
        secondary=user_roles,
        back_populates="roles",
    )

    permissions: Mapped[list["PermissionModel"]] = relationship(
        secondary=role_permissions,
        back_populates="roles",
    )


class PermissionModel(Base):
    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    key: Mapped[str] = mapped_column(String, unique=True, index=True)

    roles: Mapped[list[RoleModel]] = relationship(
        secondary=role_permissions,
        back_populates="permissions",
    )


class FeatureFlagModel(Base):
    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    dev_only: Mapped[bool] = mapped_column(Boolean, default=False)


class WorkflowItemModel(Base):
    __tablename__ = "workflow_items"
    __table_args__ = (
        Index("ix_workflow_status_severidade", "status", "severidade"),
        Index("ix_workflow_modulo_status", "modulo", "status"),
        Index("ix_workflow_militar_status", "militar_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fingerprint: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    modulo: Mapped[str] = mapped_column(String(80), index=True)
    tipo: Mapped[str] = mapped_column(String(80), index=True)
    severidade: Mapped[str] = mapped_column(String(20), index=True)
    score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    status: Mapped[str] = mapped_column(String(40), default="aberto", index=True)
    militar_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("militar.id"),
        nullable=True,
        index=True,
    )
    referencia_tipo: Mapped[str | None] = mapped_column(String(80), index=True)
    referencia_id: Mapped[str | None] = mapped_column(String(80), index=True)
    titulo: Mapped[str] = mapped_column(String(220))
    descricao: Mapped[str] = mapped_column(Text)
    acao_recomendada: Mapped[str] = mapped_column(String(120))
    motivo_regra: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by_user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    militar: Mapped["MilitarModel | None"] = relationship()


class DocumentModel(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String, index=True)
    filename: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, index=True)
    source_module: Mapped[str] = mapped_column(String, default="compilador")
    output_path: Mapped[str] = mapped_column(String)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    template_sha256: Mapped[str | None] = mapped_column(String(128), nullable=True)
    template_version: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    input_sha256: Mapped[str | None] = mapped_column(String(128), nullable=True)
    output_sha256: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    owner_user_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)

    owner: Mapped[UserModel | None] = relationship()


class CompilerRunModel(Base):
    __tablename__ = "compiler_run"
    __table_args__ = (
        Index("ix_compiler_run_tipo_status", "tipo_compilacao", "status"),
        Index("ix_compiler_run_militar_periodo", "militar_id", "ano", "semestre"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    tipo_compilacao: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    militar_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("militar.id"), nullable=True, index=True)
    nome_militar_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    identidade_snapshot: Mapped[str | None] = mapped_column(String(40), nullable=True)
    posto_grad_snapshot: Mapped[str | None] = mapped_column(String(120), nullable=True)
    periodo_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    periodo_fim: Mapped[date | None] = mapped_column(Date, nullable=True)
    ano: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    semestre: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    fonte_tempo: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fonte_eventos: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    militar: Mapped["MilitarModel | None"] = relationship()
    created_by: Mapped[UserModel | None] = relationship()
    files: Mapped[list["CompilerFileModel"]] = relationship(back_populates="run")
    variable_snapshots: Mapped[list["CompilerVariableSnapshotModel"]] = relationship(back_populates="run")
    validations: Mapped[list["CompilerValidationModel"]] = relationship(back_populates="run")


class CompilerFileModel(Base):
    __tablename__ = "compiler_file"
    __table_args__ = (
        Index("ix_compiler_file_role_sha", "role", "sha256"),
        Index("ix_compiler_file_run_role", "run_id", "role"),
        Index("ix_compiler_file_militar_role", "militar_id", "role"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String, ForeignKey("compiler_run.id"), nullable=True, index=True)
    document_id: Mapped[str | None] = mapped_column(String, ForeignKey("documents.id"), nullable=True, index=True)
    militar_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("militar.id"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(80), index=True)
    filename: Mapped[str] = mapped_column(String(255), index=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    extension: Mapped[str | None] = mapped_column(String(20), nullable=True)
    storage_path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(128), index=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_kind: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)

    run: Mapped[CompilerRunModel | None] = relationship(back_populates="files")
    document: Mapped[DocumentModel | None] = relationship()
    militar: Mapped["MilitarModel | None"] = relationship()
    variable_snapshots: Mapped[list["CompilerVariableSnapshotModel"]] = relationship(back_populates="file")
    validations: Mapped[list["CompilerValidationModel"]] = relationship(back_populates="file")


class CompilerVariableSnapshotModel(Base):
    __tablename__ = "compiler_variable_snapshot"
    __table_args__ = (
        Index("ix_compiler_snapshot_run_created", "run_id", "created_at"),
        Index("ix_compiler_snapshot_file_created", "file_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String, ForeignKey("compiler_run.id"), nullable=True, index=True)
    file_id: Mapped[str | None] = mapped_column(String, ForeignKey("compiler_file.id"), nullable=True, index=True)
    militar_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("militar.id"), nullable=True, index=True)
    schema_version: Mapped[str] = mapped_column(String(40), default="compiler-memory-v1")
    variables_json: Mapped[dict] = mapped_column(JSON)
    warnings_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    pending_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    confidence_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)

    run: Mapped[CompilerRunModel | None] = relationship(back_populates="variable_snapshots")
    file: Mapped[CompilerFileModel | None] = relationship(back_populates="variable_snapshots")
    militar: Mapped["MilitarModel | None"] = relationship()


class CompilerValidationModel(Base):
    __tablename__ = "compiler_validation"
    __table_args__ = (
        Index("ix_compiler_validation_run_level", "run_id", "level"),
        Index("ix_compiler_validation_file_code", "file_id", "code"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String, ForeignKey("compiler_run.id"), nullable=True, index=True)
    file_id: Mapped[str | None] = mapped_column(String, ForeignKey("compiler_file.id"), nullable=True, index=True)
    level: Mapped[str] = mapped_column(String(20), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    message: Mapped[str] = mapped_column(Text)
    field: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)

    run: Mapped[CompilerRunModel | None] = relationship(back_populates="validations")
    file: Mapped[CompilerFileModel | None] = relationship(back_populates="validations")


class MilitarModel(Base):
    __tablename__ = "militar"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    om: Mapped[str | None] = mapped_column(String(120), index=True)
    posto_graduacao: Mapped[str | None] = mapped_column(String(120), index=True)
    situacao_militar: Mapped[str | None] = mapped_column(String(80))
    nome_completo: Mapped[str] = mapped_column(String(200), index=True)
    nome_guerra: Mapped[str | None] = mapped_column(String(120), index=True)
    identidade: Mapped[str | None] = mapped_column(String(40), unique=True, nullable=True)
    cpf: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    cp: Mapped[str | None] = mapped_column(String(40))
    prec_cp: Mapped[str | None] = mapped_column(String(40))
    pis_pasep: Mapped[str | None] = mapped_column(String(40))
    cnh: Mapped[str | None] = mapped_column(String(40))
    titulo_numero: Mapped[str | None] = mapped_column(String(40))
    titulo_zona: Mapped[str | None] = mapped_column(String(20))
    titulo_secao: Mapped[str | None] = mapped_column(String(20))
    data_nascimento: Mapped[date | None] = mapped_column(Date)
    local_nascimento: Mapped[str | None] = mapped_column(String(120))
    nome_pai: Mapped[str | None] = mapped_column(String(200))
    nome_mae: Mapped[str | None] = mapped_column(String(200))
    estado_civil: Mapped[str | None] = mapped_column(String(40))
    data_praca: Mapped[date | None] = mapped_column(Date)
    apresentacao_om: Mapped[date | None] = mapped_column(Date)
    apresentacao_gu: Mapped[date | None] = mapped_column(Date)
    tempo_servico_anterior_anos: Mapped[int] = mapped_column(Integer, default=0)
    tempo_servico_anterior_meses: Mapped[int] = mapped_column(Integer, default=0)
    tempo_servico_anterior_dias: Mapped[int] = mapped_column(Integer, default=0)
    tempo_servico_publico_anos: Mapped[int] = mapped_column(Integer, default=0)
    tempo_servico_publico_meses: Mapped[int] = mapped_column(Integer, default=0)
    tempo_servico_publico_dias: Mapped[int] = mapped_column(Integer, default=0)
    ultima_promocao: Mapped[date | None] = mapped_column(Date)
    secao: Mapped[str | None] = mapped_column(String(120), index=True)
    funcao: Mapped[str | None] = mapped_column(String(120), index=True)
    endereco: Mapped[str | None] = mapped_column(Text)
    ramal: Mapped[str | None] = mapped_column(String(40))
    telefone: Mapped[str | None] = mapped_column(String(40))
    celular: Mapped[str | None] = mapped_column(String(40))
    contato_emergencia: Mapped[str | None] = mapped_column(String(80))
    email: Mapped[str | None] = mapped_column(String(200))
    religiao: Mapped[str | None] = mapped_column(String(80))
    status_servico: Mapped[str | None] = mapped_column(String(120))
    foto_path: Mapped[str | None] = mapped_column(String(255))
    observacoes: Mapped[str | None] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    tarefas: Mapped[list["TarefaModel"]] = relationship(back_populates="militar")
    folhas: Mapped[list["FolhaAlteracaoModel"]] = relationship(back_populates="militar")
    calculos: Mapped[list["CalculoTempoServicoModel"]] = relationship(back_populates="militar")
    ctsms: Mapped[list["CTSMModel"]] = relationship(back_populates="militar")

    periodos_servico: Mapped[list["MilitarPeriodoServicoModel"]] = relationship(
        back_populates="militar",
        cascade="all, delete-orphan",
    )

    situacao_regulamentar: Mapped[str | None] = mapped_column(String(120))
    qas_qms: Mapped[str | None] = mapped_column(String(160))
    rm: Mapped[str | None] = mapped_column(String(80))
    local_om: Mapped[str | None] = mapped_column(String(200))
    data_turma: Mapped[date | None] = mapped_column(Date)
    comportamento: Mapped[str | None] = mapped_column(String(40))

    sexo: Mapped[str | None] = mapped_column(String(40))
    escolaridade: Mapped[str | None] = mapped_column(String(120))
    nacionalidade: Mapped[str | None] = mapped_column(String(120))
    data_falecimento: Mapped[date | None] = mapped_column(Date)
    identidade_civil: Mapped[str | None] = mapped_column(String(60))
    categoria: Mapped[str | None] = mapped_column(String(80))
    autodeclaracao_etnico_racial: Mapped[str | None] = mapped_column(String(120))
    ra: Mapped[str | None] = mapped_column(String(60))
    tipo_sanguineo: Mapped[str | None] = mapped_column(String(10))
    fator_rh: Mapped[str | None] = mapped_column(String(10))
    doador_orgaos: Mapped[str | None] = mapped_column(String(40))

    data_incorporacao: Mapped[date | None] = mapped_column(Date)
    data_engajamento: Mapped[date | None] = mapped_column(Date)
    data_reengajamento: Mapped[date | None] = mapped_column(Date)
    data_desengajamento: Mapped[date | None] = mapped_column(Date)
    data_licenciamento: Mapped[date | None] = mapped_column(Date)
    data_exclusao_servico_ativo: Mapped[date | None] = mapped_column(Date)

    observacoes_calculo: Mapped[str | None] = mapped_column(Text)
    ficha_cadastro_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ficha_cadastro_pdf_hash: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )
    ficha_cadastro_origem: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ficha_cadastro_importado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MissaoModel(Base):
    __tablename__ = "missao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str | None] = mapped_column(String(40), unique=True)
    titulo: Mapped[str] = mapped_column(String(200), index=True)
    descricao: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), index=True)
    secao: Mapped[str | None] = mapped_column(String(120), index=True)
    responsavel_user_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    prazo_inicio: Mapped[datetime | None] = mapped_column(DateTime)
    prazo_fim: Mapped[datetime | None] = mapped_column(DateTime)
    observacoes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    tarefas: Mapped[list["TarefaModel"]] = relationship(back_populates="missao")


class TarefaModel(Base):
    __tablename__ = "tarefa"
    __table_args__ = (
        Index("ix_tarefa_status_prioridade", "status", "prioridade"),
        Index("ix_tarefa_secao_status", "secao_responsavel", "status"),
        Index("ix_tarefa_referencia", "referencia_tipo", "referencia_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str | None] = mapped_column(String(40), unique=True)
    fingerprint: Mapped[str | None] = mapped_column(String(180), unique=True, nullable=True)
    titulo: Mapped[str] = mapped_column(String(200), index=True)
    descricao: Mapped[str | None] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(String(60), index=True)
    prioridade: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    origem_modulo: Mapped[str] = mapped_column(String(60), index=True)
    secao_responsavel: Mapped[str | None] = mapped_column(String(120), index=True)
    divisao_responsavel: Mapped[str | None] = mapped_column(String(120), index=True)
    referencia_tipo: Mapped[str | None] = mapped_column(String(80), index=True)
    referencia_id: Mapped[str | None] = mapped_column(String(120), index=True)
    militar_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("militar.id"),
        nullable=True,
        index=True,
    )
    missao_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("missao.id"),
        nullable=True,
        index=True,
    )
    workflow_item_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("workflow_items.id"),
        nullable=True,
        index=True,
    )
    document_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("documents.id"),
        nullable=True,
        index=True,
    )
    responsavel_user_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    revisor_user_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    criado_por_user_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    completed_by_user_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    closed_by_user_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    blocked_by_task_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tarefa.id"),
        nullable=True,
        index=True,
    )
    prazo: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    data_inicio: Mapped[datetime | None] = mapped_column(DateTime)
    data_conclusao: Mapped[datetime | None] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    bloqueada: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    motivo_bloqueio: Mapped[str | None] = mapped_column(Text)
    resultado_resumido: Mapped[str | None] = mapped_column(Text)
    artefato_tipo: Mapped[str | None] = mapped_column(String(80))
    artefato_path: Mapped[str | None] = mapped_column(String(500))
    artefato_sha256: Mapped[str | None] = mapped_column(String(128), index=True)
    checklist_json: Mapped[dict | None] = mapped_column(JSON)
    created_from_rule: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    observacoes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    militar: Mapped[MilitarModel | None] = relationship(back_populates="tarefas")
    missao: Mapped[MissaoModel | None] = relationship(back_populates="tarefas")
    workflow_item: Mapped[WorkflowItemModel | None] = relationship()
    document: Mapped[DocumentModel | None] = relationship()
    eventos: Mapped[list["TarefaEventoModel"]] = relationship(
        back_populates="tarefa",
        cascade="all, delete-orphan",
    )


class TarefaEventoModel(Base):
    __tablename__ = "tarefa_evento"
    __table_args__ = (
        Index("ix_tarefa_evento_tarefa_created", "tarefa_id", "created_at"),
        Index("ix_tarefa_evento_actor_created", "actor_user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tarefa_id: Mapped[int] = mapped_column(Integer, ForeignKey("tarefa.id"), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    before_json: Mapped[dict | None] = mapped_column(JSON)
    after_json: Mapped[dict | None] = mapped_column(JSON)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)

    tarefa: Mapped[TarefaModel] = relationship(back_populates="eventos")
    actor: Mapped[UserModel | None] = relationship()


class QuadroBoardModel(Base):
    __tablename__ = "quadro_board"
    __table_args__ = (
        Index("ix_quadro_owner_updated", "owner_user_id", "updated_at"),
        Index("ix_quadro_visibility_updated", "visibility", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    titulo: Mapped[str] = mapped_column(String(160), index=True)
    descricao: Mapped[str | None] = mapped_column(Text)
    visibility: Mapped[str] = mapped_column(String(20), default="private", index=True)
    owner_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    content_json: Mapped[dict] = mapped_column(JSON, default=dict)
    thumbnail_png: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    owner: Mapped[UserModel] = relationship()


class FolhaAlteracaoModel(Base):
    __tablename__ = "folha_alteracao"
    __table_args__ = (
        Index("ix_folha_militar_periodo", "militar_id", "periodo_inicio", "periodo_fim"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str | None] = mapped_column(String(40), unique=True)
    militar_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("militar.id"),
        index=True,
    )
    periodo_inicio: Mapped[date] = mapped_column(Date, index=True)
    periodo_fim: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    origem_dados: Mapped[str | None] = mapped_column(String(60))
    responsavel_user_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    revisor_user_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    header_json: Mapped[dict | None] = mapped_column(JSON)
    part1_json: Mapped[dict | None] = mapped_column(JSON)
    part2_json: Mapped[dict | None] = mapped_column(JSON)
    diagnostico_json: Mapped[dict | None] = mapped_column(JSON)
    odt_path: Mapped[str | None] = mapped_column(String(255))
    pdf_path: Mapped[str | None] = mapped_column(String(255))
    observacoes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    militar: Mapped[MilitarModel] = relationship(back_populates="folhas")
    eventos: Mapped[list["FolhaEventoModel"]] = relationship(back_populates="folha")


class FolhaEventoModel(Base):
    __tablename__ = "folha_evento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    folha_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("folha_alteracao.id"),
        index=True,
    )
    tipo_evento: Mapped[str] = mapped_column(String(40), index=True)
    descricao: Mapped[str] = mapped_column(Text)
    user_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    payload_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)

    folha: Mapped[FolhaAlteracaoModel] = relationship(back_populates="eventos")


class NotificacaoModel(Base):
    __tablename__ = "notificacao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.id"),
        index=True,
    )
    titulo: Mapped[str] = mapped_column(String(160))
    mensagem: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(String(40), index=True)
    referencia_tipo: Mapped[str | None] = mapped_column(String(40), index=True)
    referencia_id: Mapped[int | None] = mapped_column(Integer, index=True)
    lida: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)


class LegislacaoModel(Base):
    __tablename__ = "legislacao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str | None] = mapped_column(String(40), unique=True)
    titulo: Mapped[str] = mapped_column(String(240), index=True)
    tipo: Mapped[str] = mapped_column(String(40), index=True)
    orgao: Mapped[str | None] = mapped_column(String(120))
    numero: Mapped[str | None] = mapped_column(String(40))
    ano: Mapped[int | None] = mapped_column(Integer, index=True)
    ementa: Mapped[str | None] = mapped_column(Text)
    conteudo_resumido: Mapped[str | None] = mapped_column(Text)
    palavras_chave: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), index=True)
    vigencia_inicio: Mapped[date | None] = mapped_column(Date)
    vigencia_fim: Mapped[date | None] = mapped_column(Date)
    url_oficial: Mapped[str | None] = mapped_column(String(255))
    observacoes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    arquivos: Mapped[list["LegislacaoArquivoModel"]] = relationship(back_populates="legislacao")


class LegislacaoArquivoModel(Base):
    __tablename__ = "legislacao_arquivo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    legislacao_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("legislacao.id"),
        index=True,
    )
    nome_arquivo: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str | None] = mapped_column(String(120))
    path: Mapped[str] = mapped_column(String(255))
    hash_sha256: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)

    legislacao: Mapped[LegislacaoModel] = relationship(back_populates="arquivos")


class CalculoTempoServicoModel(Base):
    __tablename__ = "calculo_tempo_servico"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    militar_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("militar.id"),
        index=True,
    )
    referencia_data: Mapped[date] = mapped_column(Date, index=True)
    tempo_arregimentado_anos: Mapped[int] = mapped_column(Integer, default=0)
    tempo_arregimentado_meses: Mapped[int] = mapped_column(Integer, default=0)
    tempo_arregimentado_dias: Mapped[int] = mapped_column(Integer, default=0)
    tempo_nao_arregimentado_anos: Mapped[int] = mapped_column(Integer, default=0)
    tempo_nao_arregimentado_meses: Mapped[int] = mapped_column(Integer, default=0)
    tempo_nao_arregimentado_dias: Mapped[int] = mapped_column(Integer, default=0)
    tempo_computado_anos: Mapped[int] = mapped_column(Integer, default=0)
    tempo_computado_meses: Mapped[int] = mapped_column(Integer, default=0)
    tempo_computado_dias: Mapped[int] = mapped_column(Integer, default=0)
    tempo_total_anos: Mapped[int] = mapped_column(Integer, default=0)
    tempo_total_meses: Mapped[int] = mapped_column(Integer, default=0)
    tempo_total_dias: Mapped[int] = mapped_column(Integer, default=0)
    base_legal_json: Mapped[dict | None] = mapped_column(JSON)
    observacoes: Mapped[str | None] = mapped_column(Text)
    calculado_por_user_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    militar: Mapped[MilitarModel] = relationship(back_populates="calculos")


class CTSMModel(Base):
    __tablename__ = "ctsm"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str | None] = mapped_column(String(40), unique=True)
    militar_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("militar.id"),
        index=True,
    )
    calculo_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("calculo_tempo_servico.id"),
        nullable=True,
        index=True,
    )
    document_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("documents.id"),
        nullable=True,
        index=True,
    )
    folha_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("folha_alteracao.id"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(40), index=True)
    responsavel_user_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    revisor_user_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    conteudo_json: Mapped[dict | None] = mapped_column(JSON)
    odt_path: Mapped[str | None] = mapped_column(String(255))
    pdf_path: Mapped[str | None] = mapped_column(String(255))
    emitido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    emitido_por_user_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    observacoes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    militar: Mapped[MilitarModel] = relationship(back_populates="ctsms")
    calculo: Mapped[CalculoTempoServicoModel | None] = relationship()
    document: Mapped[DocumentModel | None] = relationship()


class MilitarPeriodoServicoModel(Base):
    __tablename__ = "militar_periodo_servico"
    __table_args__ = (
        Index("ix_periodo_sicapex_source_file", "source_file_id"),
        Index("ix_periodo_sicapex_hash_evento", "hash_evento"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    militar_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("militar.id"),
        index=True,
    )

    tipo_registro: Mapped[str] = mapped_column(String(60), index=True)
    subtipo_registro: Mapped[str | None] = mapped_column(String(80), index=True)
    natureza_servico: Mapped[str | None] = mapped_column(String(80), index=True)
    categoria_tempo: Mapped[str] = mapped_column(String(40), index=True)
    origem: Mapped[str | None] = mapped_column(String(80))

    data_inicio: Mapped[date] = mapped_column(Date, index=True)
    data_fim: Mapped[date | None] = mapped_column(Date, index=True)

    computa_tempo: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    arregimentado: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    dias_lancados_override: Mapped[int | None] = mapped_column(Integer)
    documento_referencia: Mapped[str | None] = mapped_column(String(160))
    status_calculo: Mapped[str | None] = mapped_column(String(40), index=True)

    om_origem: Mapped[str | None] = mapped_column(String(120))
    om_destino: Mapped[str | None] = mapped_column(String(120))

    descricao: Mapped[str | None] = mapped_column(Text)
    observacoes: Mapped[str | None] = mapped_column(Text)
    source_file_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("sicapex_import_file.id"),
        nullable=True,
        index=True,
    )
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    hash_evento: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    origem_documental: Mapped[str | None] = mapped_column(String(80), nullable=True)
    confianca_parse: Mapped[str | None] = mapped_column(String(40), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    militar: Mapped["MilitarModel"] = relationship(back_populates="periodos_servico")
    source_file: Mapped["SicapexImportFileModel | None"] = relationship()


class SicapexImportBatchModel(Base):
    __tablename__ = "sicapex_import_batch"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    source_folder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_files: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    pending_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    report_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    files: Mapped[list["SicapexImportFileModel"]] = relationship(back_populates="batch")


class SicapexImportFileModel(Base):
    __tablename__ = "sicapex_import_file"
    __table_args__ = (
        Index("ix_sicapex_file_batch_status", "batch_id", "status"),
        Index("ix_sicapex_file_sha256", "sha256"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    batch_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("sicapex_import_batch.id"),
        nullable=True,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255), index=True)
    sha256: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    militar_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("militar.id"),
        nullable=True,
        index=True,
    )
    identidade_militar_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    parsed_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)

    batch: Mapped[SicapexImportBatchModel | None] = relationship(back_populates="files")
    militar: Mapped[MilitarModel | None] = relationship()


class SicapexEventoFuncionalModel(Base):
    __tablename__ = "sicapex_evento_funcional"
    __table_args__ = (
        Index("ix_sicapex_evento_militar_tipo", "militar_id", "tipo_evento"),
        Index("ix_sicapex_evento_source_file", "source_file_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    militar_id: Mapped[int] = mapped_column(Integer, ForeignKey("militar.id"), index=True)
    source_file_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("sicapex_import_file.id"),
        nullable=True,
        index=True,
    )
    tipo_evento: Mapped[str] = mapped_column(String(80), index=True)
    subtipo_evento: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    data_inicio: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    data_fim: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    documento: Mapped[str | None] = mapped_column(String(180), nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)

    militar: Mapped[MilitarModel] = relationship()
    source_file: Mapped[SicapexImportFileModel | None] = relationship()
