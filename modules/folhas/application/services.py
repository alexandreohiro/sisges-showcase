from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from infra.persistence.models import (
    FolhaAlteracaoModel,
    FolhaEventoModel,
    MilitarModel,
    NotificacaoModel,
    UserModel,
)
from infra.persistence.transactions import atomic
from modules.folhas.application.schemas import (
    FolhaActionInput,
    FolhaCreate,
    FolhaDocumentUpdateHistoryItem,
    FolhaDocumentUpdateInput,
    FolhaDocumentUpdateRead,
    FolhaDocumentUpdateSummary,
    FolhaEventoRead,
    FolhaWorkflowRead,
)
from modules.folhas.domain.validacoes import validar_part2_schema
from modules.folhas.infrastructure.repository import FolhasRepository
from modules.documents.application.services import DocumentService
from modules.tarefas.application.schemas import TarefaCreate
from modules.tarefas.infrastructure.repository import TarefasRepository

STATUS_GERADA = "GERADA"
STATUS_EM_REVISAO_SECRETARIA = "EM_REVISAO_SECRETARIA"
STATUS_AGUARDANDO_CIENCIA_MILITAR = "AGUARDANDO_CIENCIA_MILITAR"
STATUS_DEVOLVIDA_PELO_MILITAR = "DEVOLVIDA_PELO_MILITAR"
STATUS_APROVADA_PELO_MILITAR = "APROVADA_PELO_MILITAR"
STATUS_AGUARDANDO_ASSINATURA = "AGUARDANDO_ASSINATURA"
STATUS_ASSINADA = "ASSINADA"
STATUS_ARQUIVADA = "ARQUIVADA"

ASSINATURA_STATUSES = [STATUS_AGUARDANDO_ASSINATURA]
MILITAR_VISIBLE_STATUSES = [
    STATUS_AGUARDANDO_CIENCIA_MILITAR,
    STATUS_DEVOLVIDA_PELO_MILITAR,
    STATUS_APROVADA_PELO_MILITAR,
    STATUS_AGUARDANDO_ASSINATURA,
    STATUS_ASSINADA,
    STATUS_ARQUIVADA,
]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _workflow_metadata(folha: FolhaAlteracaoModel) -> dict:
    metadata = dict(folha.diagnostico_json or {})
    workflow = dict(metadata.get("workflow") or {})
    metadata["workflow"] = workflow
    return metadata


def _workflow_value(folha: FolhaAlteracaoModel, key: str) -> str | None:
    metadata = folha.diagnostico_json or {}
    workflow = metadata.get("workflow") or {}
    value = workflow.get(key) or metadata.get(key)
    return str(value) if value else None


def _display_militar(folha: FolhaAlteracaoModel) -> str:
    militar = folha.militar
    if not militar:
        return f"militar #{folha.militar_id}"
    return militar.nome_guerra or militar.nome_completo or f"militar #{folha.militar_id}"


def _actor_id(user: dict | None) -> str | None:
    if not user:
        return None
    value = user.get("id") or user.get("user_id")
    return str(value) if value else None


def _digits(value: str | None) -> str:
    return "".join(character for character in str(value or "") if character.isdigit())


def _mask_cpf(cpf_digits: str) -> str:
    return f"***.***.***-{cpf_digits[-2:]}"


def _document_update_applied_filters(
    *,
    tipo_documento: str | None,
    ano: int | None,
    semestre: int | None,
    codom: str | None,
    cpf: str | None,
    has_upload: bool | None,
) -> dict[str, str | int | bool]:
    filters: dict[str, str | int | bool] = {}
    if tipo_documento:
        filters["tipo_documento"] = tipo_documento.strip().lower()
    if ano is not None:
        filters["ano"] = ano
    if semestre is not None:
        filters["semestre"] = semestre
    if codom and codom.strip():
        filters["codom"] = codom.strip().upper()
    if has_upload is not None:
        filters["has_upload"] = has_upload
    cpf_digits = _digits(cpf)
    if len(cpf_digits) == 11:
        filters["cpf_masked"] = _mask_cpf(cpf_digits)
    elif 0 < len(cpf_digits) <= 2:
        filters["cpf_suffix"] = cpf_digits
    elif cpf_digits:
        filters["cpf_filter"] = "invalid_partial"
    return filters


def _periodo_from_semestre(ano: int, semestre: int) -> tuple[str, str]:
    if semestre == 1:
        return f"{ano}-01-01", f"{ano}-06-30"
    return f"{ano}-07-01", f"{ano}-12-31"


def _document_update_output_dir() -> Path:
    return Path(os.getenv("SISGES_DOCUMENT_UPDATE_DIR", "data/outputs/document_updates"))


def document_update_file_dir() -> Path:
    return _document_update_output_dir() / "files"


def _user_permissions(user: dict | None) -> set[str]:
    if not user:
        return set()
    return {str(item) for item in user.get("permissions", [])}


def _is_dev(user: dict | None) -> bool:
    return bool(user and user.get("is_dev"))


def _is_manager(user: dict | None) -> bool:
    permissions = _user_permissions(user)
    return _is_dev(user) or bool(
        {
            "mod.folhas.review",
            "mod.folhas.edit",
        }
        & permissions
    )


def _is_signer(user: dict | None) -> bool:
    return _is_dev(user) or "mod.folhas.finalize" in _user_permissions(user)


def _can_view_all(user: dict | None) -> bool:
    return _is_dev(user) or "mod.folhas.view" in _user_permissions(user)


def _allowed_actions(folha: FolhaAlteracaoModel, *, own: bool, user: dict | None) -> list[str]:
    status = folha.status
    actions: list[str] = []

    if _is_manager(user):
        if status in {"rascunho", "pendente", "revisao", STATUS_GERADA, STATUS_EM_REVISAO_SECRETARIA}:
            actions.append("liberar_ciencia")
        if status == STATUS_APROVADA_PELO_MILITAR:
            actions.append("enviar_assinatura")

    if own and status == STATUS_AGUARDANDO_CIENCIA_MILITAR:
        actions.extend(["aprovar_militar", "devolver_militar"])

    if _is_signer(user) and status == STATUS_AGUARDANDO_ASSINATURA:
        signer_id = _workflow_value(folha, "assinante_user_id")
        if not signer_id or signer_id == _actor_id(user) or _is_dev(user):
            actions.append("assinar")

    return actions


class FolhasService:
    def __init__(self, db):
        self.db = db
        self.folhas_repo = FolhasRepository(db)
        self.tarefas_repo = TarefasRepository(db)

    def create_folha_with_task(self, payload: FolhaCreate, actor_user_id: str | None):
        with atomic(self.db):
            folha = self.folhas_repo.create(payload)

            titulo_tarefa = f"Revisar folha #{folha.id} do militar {folha.militar_id}"

            tarefa = self.tarefas_repo.create(
                TarefaCreate(
                    titulo=titulo_tarefa,
                    descricao=(
                        f"Folha criada para periodo "
                        f"{folha.periodo_inicio} ate {folha.periodo_fim}."
                    ),
                    tipo="folha_alteracao",
                    prioridade="media",
                    status="nova",
                    origem_modulo="folhas",
                    militar_id=folha.militar_id,
                    responsavel_user_id=folha.responsavel_user_id,
                    criado_por_user_id=actor_user_id,
                    observacoes="Tarefa gerada automaticamente na criacao da folha.",
                )
            )

            self._add_event(
                folha,
                "criada",
                f"Folha criada e tarefa #{tarefa.id} gerada automaticamente.",
                actor_user_id,
                {
                    "tarefa_id": tarefa.id,
                    "status_folha": folha.status,
                },
            )

            if folha.responsavel_user_id:
                self.db.add(
                    NotificacaoModel(
                        user_id=folha.responsavel_user_id,
                        titulo="Nova tarefa de folha",
                        mensagem=f"Voce recebeu a tarefa #{tarefa.id}: {tarefa.titulo}",
                        tipo="nova_tarefa",
                        referencia_tipo="tarefa",
                        referencia_id=tarefa.id,
                        lida=False,
                    )
                )

            self.db.flush()
            self.db.refresh(folha)
            self.db.refresh(tarefa)

        return folha, tarefa

    def resolve_user_militar(self, user: dict | None) -> MilitarModel | None:
        identidade = (user or {}).get("identidade")
        if not identidade:
            return None
        return (
            self.db.query(MilitarModel)
            .filter(MilitarModel.identidade == str(identidade))
            .first()
        )

    def list_workflows(
        self,
        *,
        status: str | None,
        scope: str,
        user: dict | None,
        limit: int,
    ) -> list[FolhaWorkflowRead]:
        militar_id: int | None = None
        statuses: list[str] | None = [status] if status else None

        if scope == "minhas":
            militar = self.resolve_user_militar(user)
            if not militar:
                return []
            militar_id = militar.id
            statuses = statuses or MILITAR_VISIBLE_STATUSES
        elif scope == "assinatura":
            statuses = statuses or ASSINATURA_STATUSES

        folhas = self.folhas_repo.list_by_statuses(
            statuses=statuses,
            militar_id=militar_id,
            limit=limit,
        )
        return [self.to_workflow_read(folha, user=user) for folha in folhas]

    def register_document_update(
        self,
        *,
        payload: FolhaDocumentUpdateInput,
        actor_user_id: str | None,
        uploaded_file_path: str | None = None,
        uploaded_filename: str | None = None,
        uploaded_mime_type: str | None = None,
        uploaded_size_bytes: int | None = None,
        uploaded_sha256: str | None = None,
        trace_id: str | None = None,
    ) -> FolhaDocumentUpdateRead:
        cpf_digits = payload.cpf
        cpf_masked = _mask_cpf(cpf_digits)
        cpf_sha256 = hashlib.sha256(cpf_digits.encode("utf-8")).hexdigest()
        periodo_inicio, periodo_fim = _periodo_from_semestre(payload.ano, payload.semestre)
        militar = self._find_militar_by_cpf(cpf_digits)
        trace_id = trace_id or uuid4().hex
        output_dir = _document_update_output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_dir = output_dir / "manifests"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_dir / f"document_update_{trace_id}.json"
        metadata = {
            "schema_version": "sisges-folhas-document-update-v1",
            "tipo_documento": payload.tipo_documento,
            "ano": payload.ano,
            "semestre": payload.semestre,
            "periodo_inicio": periodo_inicio,
            "periodo_fim": periodo_fim,
            "codom": payload.codom,
            "cpf_masked": cpf_masked,
            "cpf_sha256": cpf_sha256,
            "militar_id": militar.id if militar else None,
            "militar_nome": militar.nome_completo if militar else None,
            "militar_identidade": militar.identidade if militar else None,
            "requested_by_user_id": actor_user_id,
            "observacao": payload.observacao,
            "warning": "CPF bruto nao e persistido no manifesto operacional.",
            "manifest_path": str(manifest_path),
            "uploaded_file": {
                "filename": uploaded_filename,
                "storage_path": uploaded_file_path,
                "mime_type": uploaded_mime_type,
                "size_bytes": uploaded_size_bytes,
                "sha256": uploaded_sha256,
            }
            if uploaded_file_path
            else None,
        }
        manifest_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        output_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

        document = DocumentService(self.db).register_document(
            kind=f"{payload.tipo_documento.upper()}_UPDATE_REQUEST",
            filename=uploaded_filename or manifest_path.name,
            status="DOC_UPDATE_REGISTERED",
            source_module="folhas.document_update",
            output_path=uploaded_file_path or str(manifest_path),
            owner_user_id=actor_user_id,
            trace_id=trace_id,
            output_sha256=uploaded_sha256 or output_sha256,
            metadata=metadata,
        )

        return FolhaDocumentUpdateRead(
            document_id=document.id,
            status=document.status,
            tipo_documento=payload.tipo_documento,
            ano=payload.ano,
            semestre=payload.semestre,
            codom=payload.codom,
            cpf_masked=cpf_masked,
            militar_id=militar.id if militar else None,
            militar_nome=militar.nome_completo if militar else None,
            output_path=uploaded_file_path or str(manifest_path),
            message="Atualizacao documental registrada no historico do SISGES.",
            uploaded_filename=uploaded_filename,
            uploaded_sha256=uploaded_sha256,
        )

    def list_document_updates(
        self,
        *,
        limit: int = 50,
        tipo_documento: str | None = None,
        ano: int | None = None,
        semestre: int | None = None,
        codom: str | None = None,
        cpf: str | None = None,
        has_upload: bool | None = None,
    ) -> list[FolhaDocumentUpdateHistoryItem]:
        scan_limit = max(limit, 500)
        documents = DocumentService(self.db).repo.list_by_source_module(
            "folhas.document_update",
            limit=scan_limit,
        )
        items: list[FolhaDocumentUpdateHistoryItem] = []
        for document in documents:
            if self._document_update_matches_filters(
                document,
                tipo_documento=tipo_documento,
                ano=ano,
                semestre=semestre,
                codom=codom,
                cpf=cpf,
                has_upload=has_upload,
            ):
                items.append(self._document_update_to_history_item(document))
            if len(items) >= limit:
                break
        return items

    def summarize_document_updates(
        self,
        *,
        limit: int = 5000,
        tipo_documento: str | None = None,
        ano: int | None = None,
        semestre: int | None = None,
        codom: str | None = None,
        cpf: str | None = None,
        has_upload: bool | None = None,
    ) -> FolhaDocumentUpdateSummary:
        items_with_limit_probe = self.list_document_updates(
            limit=limit + 1,
            tipo_documento=tipo_documento,
            ano=ano,
            semestre=semestre,
            codom=codom,
            cpf=cpf,
            has_upload=has_upload,
        )
        is_limited = len(items_with_limit_probe) > limit
        items = items_with_limit_probe[:limit]
        by_tipo_documento: dict[str, int] = {}
        by_status: dict[str, int] = {}
        with_attachment = 0
        with_manifest = 0
        created_dates = [item.created_at for item in items if item.created_at is not None]

        for item in items:
            by_tipo_documento[item.tipo_documento] = by_tipo_documento.get(item.tipo_documento, 0) + 1
            by_status[item.status] = by_status.get(item.status, 0) + 1
            if item.has_attachment:
                with_attachment += 1
            if item.has_manifest:
                with_manifest += 1

        return FolhaDocumentUpdateSummary(
            total=len(items),
            with_attachment=with_attachment,
            without_attachment=len(items) - with_attachment,
            with_manifest=with_manifest,
            is_limited=is_limited,
            oldest_created_at=min(created_dates) if created_dates else None,
            latest_created_at=max(created_dates) if created_dates else None,
            applied_filters=_document_update_applied_filters(
                tipo_documento=tipo_documento,
                ano=ano,
                semestre=semestre,
                codom=codom,
                cpf=cpf,
                has_upload=has_upload,
            ),
            by_tipo_documento=by_tipo_documento,
            by_status=by_status,
            limit=limit,
        )

    def to_workflow_read(self, folha: FolhaAlteracaoModel, *, user: dict | None) -> FolhaWorkflowRead:
        militar = folha.militar
        own = bool(
            militar
            and user
            and user.get("identidade")
            and militar.identidade == user.get("identidade")
        )
        base = {
            "id": folha.id,
            "codigo": folha.codigo,
            "militar_id": folha.militar_id,
            "periodo_inicio": folha.periodo_inicio,
            "periodo_fim": folha.periodo_fim,
            "status": folha.status,
            "origem_dados": folha.origem_dados,
            "responsavel_user_id": folha.responsavel_user_id,
            "revisor_user_id": folha.revisor_user_id,
            "header_json": folha.header_json,
            "part1_json": folha.part1_json,
            "part2_json": folha.part2_json,
            "diagnostico_json": folha.diagnostico_json,
            "odt_path": folha.odt_path,
            "pdf_path": folha.pdf_path,
            "observacoes": folha.observacoes,
            "created_at": folha.created_at,
            "updated_at": folha.updated_at,
            "militar_nome": militar.nome_completo if militar else f"Militar #{folha.militar_id}",
            "militar_nome_guerra": militar.nome_guerra if militar else None,
            "militar_posto_graduacao": militar.posto_graduacao if militar else None,
            "militar_identidade": militar.identidade if militar else None,
            "document_id": _workflow_value(folha, "document_id"),
            "compiler_run_id": _workflow_value(folha, "compiler_run_id"),
            "assinatura_user_id": _workflow_value(folha, "assinante_user_id"),
            "eventos": [
                FolhaEventoRead.model_validate(event)
                for event in sorted(folha.eventos, key=lambda item: item.created_at)
            ],
            "acoes_permitidas": _allowed_actions(folha, own=own, user=user),
        }
        return FolhaWorkflowRead.model_validate(base)

    def ensure_user_can_access_folha(self, folha: FolhaAlteracaoModel, user: dict | None) -> None:
        if _can_view_all(user):
            return

        militar = folha.militar
        user_identidade = (user or {}).get("identidade")
        if militar and user_identidade and militar.identidade == user_identidade:
            if folha.status in MILITAR_VISIBLE_STATUSES:
                return

        signer_id = _workflow_value(folha, "assinante_user_id")
        if _is_signer(user) and signer_id and signer_id == _actor_id(user):
            return

        raise PermissionError("Usuario nao possui acesso a esta folha.")

    def _find_militar_by_cpf(self, cpf_digits: str) -> MilitarModel | None:
        candidates = self.db.query(MilitarModel).filter(MilitarModel.cpf.isnot(None)).all()
        for militar in candidates:
            if _digits(militar.cpf) == cpf_digits:
                return militar
        return None

    def _document_update_to_history_item(self, document) -> FolhaDocumentUpdateHistoryItem:
        metadata = document.metadata_json or {}
        uploaded_file = metadata.get("uploaded_file") or {}
        uploaded_path = uploaded_file.get("storage_path")
        return FolhaDocumentUpdateHistoryItem(
            document_id=document.id,
            status=document.status,
            tipo_documento=str(metadata.get("tipo_documento") or document.kind),
            ano=metadata.get("ano"),
            semestre=metadata.get("semestre"),
            codom=metadata.get("codom"),
            cpf_masked=metadata.get("cpf_masked"),
            militar_id=metadata.get("militar_id"),
            militar_nome=metadata.get("militar_nome"),
            output_sha256=document.output_sha256,
            uploaded_filename=uploaded_file.get("filename"),
            uploaded_sha256=uploaded_file.get("sha256"),
            has_attachment=bool(uploaded_path),
            has_manifest=bool(metadata.get("manifest_path")),
            trace_id=document.trace_id,
            created_at=document.created_at,
        )

    def _document_update_matches_filters(
        self,
        document,
        *,
        tipo_documento: str | None,
        ano: int | None,
        semestre: int | None,
        codom: str | None,
        cpf: str | None,
        has_upload: bool | None,
    ) -> bool:
        metadata = document.metadata_json or {}
        uploaded_file = metadata.get("uploaded_file") or {}

        if tipo_documento and str(metadata.get("tipo_documento") or "").lower() != tipo_documento.strip().lower():
            return False
        if ano is not None and metadata.get("ano") != ano:
            return False
        if semestre is not None and metadata.get("semestre") != semestre:
            return False
        if codom and codom.strip().upper() not in str(metadata.get("codom") or "").upper():
            return False
        if has_upload is not None and bool(uploaded_file.get("storage_path")) != has_upload:
            return False
        if cpf and not self._document_update_matches_cpf(metadata, cpf):
            return False
        return True

    def _document_update_matches_cpf(self, metadata: dict, cpf: str) -> bool:
        cpf_digits = _digits(cpf)
        if not cpf_digits:
            return True
        if len(cpf_digits) == 11:
            return metadata.get("cpf_sha256") == hashlib.sha256(cpf_digits.encode("utf-8")).hexdigest()
        if len(cpf_digits) <= 2:
            return str(metadata.get("cpf_masked") or "").endswith(cpf_digits)
        return False

    def update_folha(self, folha_id: int, payload) -> FolhaAlteracaoModel | None:
        folha = self.folhas_repo.get(folha_id)
        if not folha:
            return None
        data = payload.model_dump(exclude_unset=True)
        if data.get("part2_json") is not None:
            erros = validar_part2_schema(data["part2_json"])
            if erros:
                raise ValueError(erros[0])
        for key, value in data.items():
            setattr(folha, key, value)
        self.db.add(folha)
        self.db.flush()
        return folha

    def liberar_ciencia(
        self,
        folha_id: int,
        payload: FolhaActionInput,
        actor_user_id: str | None,
    ) -> FolhaAlteracaoModel:
        # Gate de completude: sem 2a Parte estruturalmente valida a folha
        # nao pode seguir para ciencia do militar (Port. 063-DGP/2020 Art. 24).
        folha = self._get_or_raise(folha_id)
        erros = validar_part2_schema(folha.part2_json)
        if erros:
            raise ValueError(f"Folha sem 2a Parte valida para liberar ciencia: {erros[0]}")
        return self._transition(
            folha_id,
            action="liberar_ciencia",
            new_status=STATUS_AGUARDANDO_CIENCIA_MILITAR,
            actor_user_id=actor_user_id,
            observacao=payload.observacao,
            allowed_statuses={
                "rascunho",
                "pendente",
                "revisao",
                STATUS_GERADA,
                STATUS_EM_REVISAO_SECRETARIA,
            },
        )

    def aprovar_militar(self, folha_id: int, payload: FolhaActionInput, user: dict):
        folha = self._get_or_raise(folha_id)
        self._ensure_user_owns_folha(folha, user)
        return self._transition(
            folha_id,
            action="aprovar_militar",
            new_status=STATUS_APROVADA_PELO_MILITAR,
            actor_user_id=_actor_id(user),
            observacao=payload.observacao,
            allowed_statuses={STATUS_AGUARDANDO_CIENCIA_MILITAR},
        )

    def devolver_militar(self, folha_id: int, payload: FolhaActionInput, user: dict):
        if not payload.observacao:
            raise ValueError("Observacao obrigatoria para devolver a folha.")
        folha = self._get_or_raise(folha_id)
        self._ensure_user_owns_folha(folha, user)
        return self._transition(
            folha_id,
            action="devolver_militar",
            new_status=STATUS_DEVOLVIDA_PELO_MILITAR,
            actor_user_id=_actor_id(user),
            observacao=payload.observacao,
            allowed_statuses={STATUS_AGUARDANDO_CIENCIA_MILITAR},
        )

    def enviar_assinatura(
        self,
        folha_id: int,
        payload: FolhaActionInput,
        actor_user_id: str | None,
    ):
        return self._transition(
            folha_id,
            action="enviar_assinatura",
            new_status=STATUS_AGUARDANDO_ASSINATURA,
            actor_user_id=actor_user_id,
            observacao=payload.observacao,
            allowed_statuses={STATUS_APROVADA_PELO_MILITAR},
            workflow_updates={"assinante_user_id": payload.assinante_user_id},
        )

    def assinar(self, folha_id: int, payload: FolhaActionInput, user: dict):
        folha = self._get_or_raise(folha_id)
        signer_id = _workflow_value(folha, "assinante_user_id")
        actor_user_id = _actor_id(user)
        if signer_id and signer_id != actor_user_id and not _is_dev(user):
            raise PermissionError("Folha atribuida a outro assinante.")
        workflow_updates = (
            {"modalidade_assinatura": payload.modalidade_assinatura}
            if payload.modalidade_assinatura
            else None
        )
        return self._transition(
            folha_id,
            action="assinar",
            new_status=STATUS_ASSINADA,
            actor_user_id=actor_user_id,
            observacao=payload.observacao,
            allowed_statuses={STATUS_AGUARDANDO_ASSINATURA},
            workflow_updates=workflow_updates,
        )

    def _get_or_raise(self, folha_id: int) -> FolhaAlteracaoModel:
        folha = self.folhas_repo.get(folha_id)
        if not folha:
            raise ValueError("Folha nao encontrada.")
        return folha

    def _ensure_user_owns_folha(self, folha: FolhaAlteracaoModel, user: dict):
        if _is_dev(user):
            return
        militar = folha.militar
        user_identidade = user.get("identidade")
        if not militar or not user_identidade or militar.identidade != user_identidade:
            raise PermissionError("Usuario nao vinculado ao militar desta folha.")

    def _transition(
        self,
        folha_id: int,
        *,
        action: str,
        new_status: str,
        actor_user_id: str | None,
        observacao: str | None,
        allowed_statuses: set[str],
        workflow_updates: dict | None = None,
    ) -> FolhaAlteracaoModel:
        with atomic(self.db):
            folha = self._get_or_raise(folha_id)
            previous_status = folha.status
            if previous_status not in allowed_statuses:
                raise ValueError(f"Transicao invalida para status {previous_status}.")

            metadata = _workflow_metadata(folha)
            workflow = metadata["workflow"]
            workflow.update(workflow_updates or {})
            workflow["last_action"] = action
            workflow["last_actor_user_id"] = actor_user_id
            workflow["last_action_at"] = _now_iso()
            workflow["previous_status"] = previous_status
            workflow["status"] = new_status

            folha.status = new_status
            folha.diagnostico_json = metadata
            if observacao:
                folha.observacoes = observacao

            self._add_event(
                folha,
                action,
                f"Status alterado de {previous_status} para {new_status}.",
                actor_user_id,
                {
                    "previous_status": previous_status,
                    "new_status": new_status,
                    "observacao": observacao,
                    "workflow": workflow,
                },
            )
            self._add_transition_notifications(
                folha=folha,
                action=action,
                actor_user_id=actor_user_id,
                signer_user_id=workflow.get("assinante_user_id"),
            )
            self.db.flush()
            self.db.refresh(folha)
            return folha

    def _add_event(
        self,
        folha: FolhaAlteracaoModel,
        action: str,
        description: str,
        actor_user_id: str | None,
        payload: dict | None = None,
    ) -> None:
        self.db.add(
            FolhaEventoModel(
                folha_id=folha.id,
                tipo_evento=action,
                descricao=description,
                user_id=actor_user_id,
                payload_json=payload or {},
            )
        )

    def _add_transition_notifications(
        self,
        *,
        folha: FolhaAlteracaoModel,
        action: str,
        actor_user_id: str | None,
        signer_user_id: str | None,
    ) -> None:
        militar_label = _display_militar(folha)

        if action == "liberar_ciencia":
            self._notify_users(
                self._militar_user_ids(folha),
                "Folha liberada para ciencia",
                f"A folha de alteracoes de {militar_label} esta aguardando ciencia.",
                actor_user_id,
                folha.id,
            )
        elif action == "aprovar_militar":
            self._notify_users(
                self._secretaria_user_ids(folha),
                "Folha aprovada pelo militar",
                f"{militar_label} aprovou a folha de alteracoes.",
                actor_user_id,
                folha.id,
            )
        elif action == "devolver_militar":
            self._notify_users(
                self._secretaria_user_ids(folha),
                "Folha devolvida pelo militar",
                f"{militar_label} devolveu a folha de alteracoes para revisao.",
                actor_user_id,
                folha.id,
            )
        elif action == "enviar_assinatura" and signer_user_id:
            self._notify_users(
                [str(signer_user_id)],
                "Folha aguardando assinatura",
                f"A folha de alteracoes de {militar_label} esta pronta para assinatura.",
                actor_user_id,
                folha.id,
            )
        elif action == "assinar":
            self._notify_users(
                [*self._secretaria_user_ids(folha), *self._militar_user_ids(folha)],
                "Folha assinada",
                f"A folha de alteracoes de {militar_label} foi assinada.",
                actor_user_id,
                folha.id,
            )

    def _militar_user_ids(self, folha: FolhaAlteracaoModel) -> list[str]:
        militar = folha.militar
        if not militar or not militar.identidade:
            return []
        users = (
            self.db.query(UserModel)
            .filter(
                UserModel.identidade == militar.identidade,
                UserModel.is_active.is_(True),
            )
            .all()
        )
        return [str(user.id) for user in users]

    def _secretaria_user_ids(self, folha: FolhaAlteracaoModel) -> list[str]:
        user_ids = {
            value
            for value in [folha.responsavel_user_id, folha.revisor_user_id]
            if value
        }
        return [str(user_id) for user_id in user_ids]

    def _notify_users(
        self,
        user_ids: list[str],
        title: str,
        message: str,
        actor_user_id: str | None,
        folha_id: int,
    ) -> None:
        unique_user_ids = sorted({user_id for user_id in user_ids if user_id and user_id != actor_user_id})
        for user_id in unique_user_ids:
            self.db.add(
                NotificacaoModel(
                    user_id=user_id,
                    titulo=title,
                    mensagem=message,
                    tipo="folha_alteracao",
                    referencia_tipo="folha",
                    referencia_id=folha_id,
                    lida=False,
                )
            )
