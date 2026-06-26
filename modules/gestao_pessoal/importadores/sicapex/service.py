from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
import hashlib
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from infra.persistence.models import (
    MilitarModel,
    MilitarPeriodoServicoModel,
    SicapexEventoFuncionalModel,
    SicapexImportBatchModel,
    SicapexImportFileModel,
)
from modules.gestao_pessoal.importadores.sicapex.parser import (
    identity_hash,
    mask_identity,
    record_to_safe_dict,
)
from modules.gestao_pessoal.importadores.sicapex.report import report_to_dict
from modules.gestao_pessoal.importadores.sicapex.schemas import (
    SicapexAfastamento,
    SicapexBatchReport,
    SicapexImportResult,
    SicapexMovimentacao,
    SicapexParsedRecord,
    SicapexPeriodoServicoSugerido,
    SicapexSituacaoRegulamentar,
    SicapexTempoServico,
)
from shared.utils.qms import normalize_qas_qms_qm_for_header


class SicapexImportService:
    def __init__(self, db: Session):
        self.db = db

    def create_batch(self, *, source_folder: str = "") -> SicapexImportBatchModel:
        batch = SicapexImportBatchModel(id=str(uuid4()), source_folder=source_folder)
        self.db.add(batch)
        self.db.flush()
        return batch

    def get_batch_report(self, batch_id: str) -> dict | None:
        batch = self.db.query(SicapexImportBatchModel).filter_by(id=batch_id).first()
        return batch.report_json if batch else None

    def has_sha(self, sha256: str) -> bool:
        return self.db.query(SicapexImportFileModel).filter_by(sha256=sha256).first() is not None

    def get_file_by_sha(self, sha256: str) -> SicapexImportFileModel | None:
        return self.db.query(SicapexImportFileModel).filter_by(sha256=sha256).first()

    def persist_record(
        self,
        *,
        record: SicapexParsedRecord,
        pdf_path: Path,
        batch_id: str | None,
        dry_run: bool,
        refresh_existing: bool = False,
    ) -> SicapexImportResult:
        if record.ocr_required:
            return self._result(record, pdf_path, "OCR_REQUIRED", errors=["Texto extraido vazio."])

        existing_file = self.get_file_by_sha(record.source_sha256)
        if existing_file and not refresh_existing:
            return self._result(record, pdf_path, "DUPLICATE_SHA", militar_id=existing_file.militar_id)

        existing = self._find_existing(record)
        divergent = self._has_divergent_name(existing, record)
        if divergent:
            return self._result(
                record,
                pdf_path,
                "DIVERGENT_IDENTITY_NAME",
                militar_id=existing.id if existing else None,
                errors=["Identidade militar ja existe com nome divergente."],
            )

        if dry_run:
            status = "PENDING" if record.pending else "DRY_RUN_OK"
            return self._result(record, pdf_path, status, militar_id=existing.id if existing else None)

        militar = self._upsert_militar(record, existing)
        status = "PENDING" if record.pending else "SUCCESS"
        file_model = (
            self._refresh_file_record(
                file_model=existing_file,
                record=record,
                pdf_path=pdf_path,
                batch_id=batch_id,
                status=status,
                militar_id=militar.id,
            )
            if existing_file
            else self._create_file_record(
                record=record,
                pdf_path=pdf_path,
                batch_id=batch_id,
                status=status,
                militar_id=militar.id,
            )
        )
        eventos_criados = self._replace_events(militar.id, file_model.id, record)
        periodos_criados = self._replace_periodos(militar.id, file_model.id, record)
        return self._result(
            record,
            pdf_path,
            status,
            militar_id=militar.id,
            eventos_funcionais_criados=eventos_criados,
            periodos_servico_criados=periodos_criados,
        )

    def persist_failure(
        self,
        *,
        filename: str,
        sha256: str,
        batch_id: str | None,
        error: str,
        dry_run: bool,
    ) -> SicapexImportResult:
        if not dry_run:
            file_model = SicapexImportFileModel(
                id=str(uuid4()),
                batch_id=batch_id,
                filename=filename,
                sha256=sha256,
                status="FAILED",
                error_message=error[:1000],
                warnings_json=[],
                parsed_json={},
            )
            self.db.add(file_model)
            self.db.flush()
        return SicapexImportResult(filename=filename, sha256=sha256, status="FAILED", errors=[error])

    def finalize_batch(self, report: SicapexBatchReport) -> None:
        batch = self.db.query(SicapexImportBatchModel).filter_by(id=report.batch_id).first()
        if not batch:
            return
        batch.total_files = report.total_files
        batch.success_count = report.success_count
        batch.failed_count = report.failed_count
        batch.pending_count = report.pending_count
        batch.duplicate_count = report.duplicate_count
        batch.report_json = report_to_dict(report)
        self.db.flush()

    def _find_existing(self, record: SicapexParsedRecord) -> MilitarModel | None:
        if record.identidade_militar:
            existing = (
                self.db.query(MilitarModel)
                .filter(MilitarModel.identidade == record.identidade_militar)
                .first()
            )
            if existing:
                return existing
        if record.prec_cp:
            return self.db.query(MilitarModel).filter(MilitarModel.prec_cp == record.prec_cp).first()
        if record.nome_completo:
            return (
                self.db.query(MilitarModel)
                .filter(MilitarModel.nome_completo == record.nome_completo)
                .first()
            )
        return None

    def _has_divergent_name(
        self,
        existing: MilitarModel | None,
        record: SicapexParsedRecord,
    ) -> bool:
        if not existing or not existing.nome_completo or not record.nome_completo:
            return False
        return existing.nome_completo.strip().upper() != record.nome_completo.strip().upper()

    def _upsert_militar(
        self,
        record: SicapexParsedRecord,
        existing: MilitarModel | None,
    ) -> MilitarModel:
        qms_result = normalize_qas_qms_qm_for_header(record.qas_qms_qm)
        qas_qms_value = choose_qms_for_upsert(
            existing.qas_qms if existing else None,
            qms_result.display,
            qms_result.status,
        )
        payload = {
            "nome_completo": record.nome_completo or "NOME PENDENTE SICAPEX",
            "nome_guerra": record.nome_guerra or None,
            "sexo": record.sexo or None,
            "estado_civil": record.estado_civil or None,
            "posto_graduacao": record.posto_grad_abrev or record.posto_grad_extenso or None,
            "qas_qms": qas_qms_value,
            "om": record.om_atual_nome or None,
            "local_om": record.om_atual_codom or None,
            "apresentacao_om": record.data_inicio_om,
            "apresentacao_gu": record.apresentacao_gu,
            "situacao_militar": record.situacao_militar or None,
            "status_servico": record.situacao_servico or None,
            "identidade": record.identidade_militar or None,
            "prec_cp": record.prec_cp or None,
            "data_praca": record.data_praca,
            "data_incorporacao": record.data_incorporacao or record.data_praca,
            "data_engajamento": record.data_engajamento,
            "data_reengajamento": record.data_reengajamento,
            "data_desengajamento": record.data_desengajamento,
            "data_licenciamento": record.data_licenciamento,
            "data_exclusao_servico_ativo": record.data_exclusao_servico_ativo,
            "ultima_promocao": record.ultima_promocao,
            "tempo_servico_anterior_anos": record.tempo_servico_anterior_anos,
            "tempo_servico_anterior_meses": record.tempo_servico_anterior_meses,
            "tempo_servico_anterior_dias": record.tempo_servico_anterior_dias,
            "tempo_servico_publico_anos": record.tempo_servico_publico_anos,
            "tempo_servico_publico_meses": record.tempo_servico_publico_meses,
            "tempo_servico_publico_dias": record.tempo_servico_publico_dias,
            "observacoes_calculo": record.observacoes_calculo or None,
            "comportamento": record.comportamento_atual.tipo if record.comportamento_atual else None,
            "ficha_cadastro_json": record_to_safe_dict(record),
            "ficha_cadastro_pdf_hash": record.source_sha256,
            "ficha_cadastro_origem": record.source_filename,
            "ficha_cadastro_importado_em": datetime.now(UTC),
            "observacoes": "Importado de Ficha Cadastro SiCaPEx.",
            "ativo": True,
        }
        if existing:
            for key, value in payload.items():
                if value is not None:
                    setattr(existing, key, value)
            self.db.flush()
            self.db.refresh(existing)
            return existing
        militar = MilitarModel(**payload)
        self.db.add(militar)
        self.db.flush()
        self.db.refresh(militar)
        return militar

    def _create_file_record(
        self,
        *,
        record: SicapexParsedRecord,
        pdf_path: Path,
        batch_id: str | None,
        status: str,
        militar_id: int | None,
    ) -> SicapexImportFileModel:
        file_model = SicapexImportFileModel(
            id=str(uuid4()),
            batch_id=batch_id,
            filename=pdf_path.name,
            sha256=record.source_sha256,
            status=status,
            militar_id=militar_id,
            identidade_militar_hash=identity_hash(record.identidade_militar),
            warnings_json=record.warnings + record.pending,
            parsed_json=record_to_safe_dict(record),
        )
        self.db.add(file_model)
        self.db.flush()
        return file_model

    def _refresh_file_record(
        self,
        *,
        file_model: SicapexImportFileModel,
        record: SicapexParsedRecord,
        pdf_path: Path,
        batch_id: str | None,
        status: str,
        militar_id: int | None,
    ) -> SicapexImportFileModel:
        file_model.batch_id = batch_id or file_model.batch_id
        file_model.filename = pdf_path.name
        file_model.status = status
        file_model.militar_id = militar_id
        file_model.identidade_militar_hash = identity_hash(record.identidade_militar)
        file_model.error_message = None
        file_model.warnings_json = record.warnings + record.pending
        file_model.parsed_json = record_to_safe_dict(record)
        self.db.flush()
        return file_model

    def _replace_events(self, militar_id: int, source_file_id: str, record: SicapexParsedRecord) -> int:
        self.db.query(SicapexEventoFuncionalModel).filter_by(source_file_id=source_file_id).delete()
        created = 0
        for collection, tipo in (
            (record.afastamentos, "AFASTAMENTO"),
            (record.movimentacoes, "MOVIMENTACAO"),
            (record.situacoes_regulamentares, "SITUACAO_REGULAMENTAR"),
            (record.agregacoes, "AGREGACAO"),
            (record.desconto_tempo_servico, "DESCONTO_TEMPO"),
            (record.acrescimos_tempo_servico, "ACRESCIMO_TEMPO"),
        ):
            for item in collection:
                self.db.add(self._event_model(militar_id, source_file_id, tipo, item))
                created += 1
        self.db.flush()
        return created

    def _event_model(
        self,
        militar_id: int,
        source_file_id: str,
        tipo: str,
        item: SicapexAfastamento | SicapexMovimentacao | SicapexSituacaoRegulamentar | SicapexTempoServico | dict[str, Any],
    ) -> SicapexEventoFuncionalModel:
        payload = asdict(item) if is_dataclass(item) else dict(item)
        return SicapexEventoFuncionalModel(
            militar_id=militar_id,
            source_file_id=source_file_id,
            tipo_evento=tipo,
            subtipo_evento=(
                payload.get("modalidade")
                or payload.get("situacao")
                or payload.get("subtipo")
                or payload.get("tipo")
                or None
            ),
            data_inicio=payload.get("data_inicio"),
            data_fim=payload.get("data_fim"),
            documento=payload.get("documento") or payload.get("documento_referencia") or None,
            payload_json=record_payload_json(payload),
        )

    def _replace_periodos(self, militar_id: int, source_file_id: str, record: SicapexParsedRecord) -> int:
        self.db.query(MilitarPeriodoServicoModel).filter_by(source_file_id=source_file_id).delete()
        created = 0
        for item in record.periodos_servico_sugeridos:
            if not item.data_inicio:
                continue
            periodo = self._periodo_model(militar_id, source_file_id, record.source_sha256, item)
            if self._periodo_hash_exists(periodo.hash_evento):
                continue
            self.db.add(periodo)
            created += 1
        self.db.flush()
        return created

    def _periodo_hash_exists(self, hash_evento: str | None) -> bool:
        if not hash_evento:
            return False
        return (
            self.db.query(MilitarPeriodoServicoModel.id)
            .filter(MilitarPeriodoServicoModel.hash_evento == hash_evento)
            .first()
            is not None
        )

    def _periodo_model(
        self,
        militar_id: int,
        source_file_id: str,
        source_sha256: str,
        item: SicapexPeriodoServicoSugerido,
    ) -> MilitarPeriodoServicoModel:
        payload = asdict(item)
        hash_evento = build_event_hash(
            militar_id=militar_id,
            tipo_registro=item.tipo_registro,
            subtipo_registro=item.subtipo_registro,
            data_inicio=item.data_inicio.isoformat() if item.data_inicio else "",
            data_fim=item.data_fim.isoformat() if item.data_fim else "",
            documento_referencia=item.documento_referencia,
            origem=item.origem,
            source_file_sha=source_sha256,
        )
        return MilitarPeriodoServicoModel(
            militar_id=militar_id,
            tipo_registro=item.tipo_registro,
            subtipo_registro=item.subtipo_registro or None,
            natureza_servico=item.natureza_servico or None,
            categoria_tempo=item.categoria_tempo,
            origem=item.origem,
            data_inicio=item.data_inicio,
            data_fim=item.data_fim,
            computa_tempo=item.computa_tempo,
            arregimentado=item.arregimentado,
            dias_lancados_override=item.dias_lancados_override,
            documento_referencia=item.documento_referencia or None,
            status_calculo=item.status_calculo,
            om_origem=item.om_origem or None,
            om_destino=item.om_destino or None,
            descricao=item.descricao or None,
            observacoes=item.observacoes or None,
            source_file_id=source_file_id,
            payload_json=record_payload_json(payload),
            hash_evento=hash_evento,
            origem_documental="sicapex_pdf",
            confianca_parse="media" if item.status_calculo.startswith("pendente") else "alta",
        )

    def _result(
        self,
        record: SicapexParsedRecord,
        pdf_path: Path,
        status: str,
        *,
        militar_id: int | None = None,
        errors: list[str] | None = None,
        eventos_funcionais_criados: int = 0,
        periodos_servico_criados: int = 0,
    ) -> SicapexImportResult:
        return SicapexImportResult(
            filename=pdf_path.name,
            sha256=record.source_sha256,
            status=status,
            militar_id=militar_id,
            militar_nome=record.nome_completo,
            identidade_mascarada=mask_identity(record.identidade_militar),
            om_atual=record.om_atual_nome,
            data_praca=record.data_praca,
            comportamento_atual=record.comportamento_atual.tipo if record.comportamento_atual else "",
            afastamentos_count=len(record.afastamentos),
            movimentacoes_count=len(record.movimentacoes),
            situacoes_regulamentares_count=len(record.situacoes_regulamentares),
            tempo_efetivo_servico_apos_ultima=record.tempo_efetivo_servico_apos_ultima,
            descontos_count=len(record.desconto_tempo_servico),
            acrescimos_count=len(record.acrescimos_tempo_servico),
            eventos_funcionais_criados=eventos_funcionais_criados,
            periodos_servico_criados=periodos_servico_criados,
            warnings=record.warnings,
            pending=record.pending,
            errors=errors or [],
        )


def record_payload_json(payload: dict) -> dict:
    clean = {}
    for key, value in payload.items():
        if hasattr(value, "isoformat"):
            clean[key] = value.isoformat()
        else:
            clean[key] = value
    return clean


def choose_qms_for_upsert(existing: str | None, incoming: str | None, incoming_status: str) -> str | None:
    existing_clean = (existing or "").strip()
    incoming_clean = (incoming or "").strip()
    if incoming_status in {"GENERIC_EMPTY", "PENDING"} and existing_clean:
        return existing_clean
    if incoming_clean:
        return incoming_clean
    return existing_clean or None


def build_event_hash(
    *,
    militar_id: int,
    tipo_registro: str,
    subtipo_registro: str,
    data_inicio: str,
    data_fim: str,
    documento_referencia: str,
    origem: str,
    source_file_sha: str,
) -> str:
    raw = "|".join(
        [
            str(militar_id),
            tipo_registro or "",
            subtipo_registro or "",
            data_inicio or "",
            data_fim or "",
            documento_referencia or "",
            origem or "",
            source_file_sha or "",
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
