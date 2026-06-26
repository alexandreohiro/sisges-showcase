from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from infra.persistence.models import CalculoTempoServicoModel, CTSMModel, MilitarModel
from infra.persistence.transactions import atomic
from modules.documents.application.services import DocumentService
from shared.utils.hashing import sha256_file
from shared.utils.strings import slugify_filename


class CTSMService:
    def __init__(self, db):
        self.db = db

    def list_items(self, *, militar_id: int | None = None, limit: int = 50) -> list[CTSMModel]:
        query = self.db.query(CTSMModel).order_by(CTSMModel.created_at.desc())
        if militar_id is not None:
            query = query.filter(CTSMModel.militar_id == militar_id)
        return query.limit(limit).all()

    def get(self, ctsm_id: int) -> CTSMModel | None:
        return self.db.query(CTSMModel).filter(CTSMModel.id == ctsm_id).first()

    def create_from_calculo(
        self,
        *,
        calculo_id: int,
        actor_user_id: str | None,
        observacoes: str | None = None,
        emitir_documento: bool = True,
    ) -> CTSMModel:
        calculo = self._get_calculo(calculo_id)
        militar = self._get_militar(calculo.militar_id)
        conteudo = self._build_conteudo(calculo=calculo, militar=militar)

        with atomic(self.db):
            ctsm = CTSMModel(
                codigo=self._next_codigo(militar_id=militar.id),
                militar_id=militar.id,
                calculo_id=calculo.id,
                status="rascunho",
                conteudo_json=conteudo,
                observacoes=observacoes,
                responsavel_user_id=actor_user_id,
            )
            self.db.add(ctsm)
            self.db.flush()

            if emitir_documento:
                self._emit_document_locked(
                    ctsm=ctsm,
                    actor_user_id=actor_user_id,
                    observacoes=observacoes,
                )

            self.db.refresh(ctsm)
            return ctsm

    def emitir_documento(
        self,
        *,
        ctsm_id: int,
        actor_user_id: str | None,
        observacoes: str | None = None,
    ) -> CTSMModel:
        ctsm = self.get(ctsm_id)
        if not ctsm:
            raise ValueError("CTSM nao encontrada.")

        with atomic(self.db):
            self._emit_document_locked(
                ctsm=ctsm,
                actor_user_id=actor_user_id,
                observacoes=observacoes,
            )
            self.db.refresh(ctsm)
            return ctsm

    def _get_calculo(self, calculo_id: int) -> CalculoTempoServicoModel:
        calculo = (
            self.db.query(CalculoTempoServicoModel)
            .filter(CalculoTempoServicoModel.id == calculo_id)
            .first()
        )
        if not calculo:
            raise ValueError("Calculo aprovado nao encontrado.")
        return calculo

    def _get_militar(self, militar_id: int) -> MilitarModel:
        militar = self.db.query(MilitarModel).filter(MilitarModel.id == militar_id).first()
        if not militar:
            raise ValueError("Militar vinculado ao calculo nao encontrado.")
        return militar

    def _build_conteudo(
        self,
        *,
        calculo: CalculoTempoServicoModel,
        militar: MilitarModel,
    ) -> dict:
        return {
            "tipo_documental": "CTSM",
            "versao_schema": "ctsm.v1",
            "militar": {
                "id": militar.id,
                "posto_graduacao": militar.posto_graduacao,
                "nome_completo": militar.nome_completo,
                "nome_guerra": militar.nome_guerra,
                "identidade": militar.identidade,
                "cpf": militar.cpf,
                "data_praca": militar.data_praca.isoformat() if militar.data_praca else None,
            },
            "calculo": {
                "id": calculo.id,
                "referencia_data": calculo.referencia_data.isoformat(),
                "tempo_arregimentado": {
                    "anos": calculo.tempo_arregimentado_anos,
                    "meses": calculo.tempo_arregimentado_meses,
                    "dias": calculo.tempo_arregimentado_dias,
                },
                "tempo_nao_arregimentado": {
                    "anos": calculo.tempo_nao_arregimentado_anos,
                    "meses": calculo.tempo_nao_arregimentado_meses,
                    "dias": calculo.tempo_nao_arregimentado_dias,
                },
                "tempo_computado": {
                    "anos": calculo.tempo_computado_anos,
                    "meses": calculo.tempo_computado_meses,
                    "dias": calculo.tempo_computado_dias,
                },
                "tempo_total": {
                    "anos": calculo.tempo_total_anos,
                    "meses": calculo.tempo_total_meses,
                    "dias": calculo.tempo_total_dias,
                },
                "base_legal_json": calculo.base_legal_json,
                "snapshot_created_at": calculo.created_at.isoformat() if calculo.created_at else None,
            },
        }

    def _emit_document_locked(
        self,
        *,
        ctsm: CTSMModel,
        actor_user_id: str | None,
        observacoes: str | None,
    ) -> None:
        output_dir = Path("data/outputs")
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_name = slugify_filename(
            (ctsm.conteudo_json or {}).get("militar", {}).get("nome_completo"),
            fallback=f"ctsm-{ctsm.id}",
        )
        output_path = output_dir / f"ctsm-{ctsm.id}-{safe_name}.txt"
        output_path.write_text(self._render_text(ctsm), encoding="utf-8")
        output_hash = sha256_file(output_path)
        trace_id = str(uuid4())

        document = DocumentService(self.db).register_document(
            kind="CTSM",
            filename=output_path.name,
            status="generated",
            source_module="ctsm",
            output_path=str(output_path).replace("\\", "/"),
            owner_user_id=actor_user_id,
            trace_id=trace_id,
            output_sha256=output_hash,
            metadata={
                "ctsm_id": ctsm.id,
                "calculo_id": ctsm.calculo_id,
                "militar_id": ctsm.militar_id,
                "schema": "ctsm.v1",
                "observacoes_emissao": observacoes,
            },
        )

        ctsm.document_id = document.id
        ctsm.odt_path = None
        ctsm.pdf_path = str(output_path).replace("\\", "/")
        ctsm.status = "emitida"
        ctsm.emitido_em = datetime.now(UTC).replace(tzinfo=None)
        ctsm.emitido_por_user_id = actor_user_id
        if observacoes:
            ctsm.observacoes = observacoes
        self.db.flush()

    @staticmethod
    def _render_text(ctsm: CTSMModel) -> str:
        content = ctsm.conteudo_json or {}
        militar = content.get("militar", {})
        calculo = content.get("calculo", {})
        tempo_total = calculo.get("tempo_total", {})
        tempo_computado = calculo.get("tempo_computado", {})
        return "\n".join(
            [
                "CERTIDAO DE TEMPO DE SERVICO MILITAR",
                f"Codigo: {ctsm.codigo or ctsm.id}",
                f"Militar: {militar.get('posto_graduacao') or ''} {militar.get('nome_completo') or ''}".strip(),
                f"Identidade: {militar.get('identidade') or ''}",
                f"Referencia do calculo: {calculo.get('referencia_data') or ''}",
                (
                    "Tempo computado: "
                    f"{tempo_computado.get('anos', 0)}a "
                    f"{tempo_computado.get('meses', 0)}m "
                    f"{tempo_computado.get('dias', 0)}d"
                ),
                (
                    "Tempo total: "
                    f"{tempo_total.get('anos', 0)}a "
                    f"{tempo_total.get('meses', 0)}m "
                    f"{tempo_total.get('dias', 0)}d"
                ),
                "",
                "Documento emitido pelo SISGES com base no snapshot aprovado do calculo.",
            ]
        )

    @staticmethod
    def _next_codigo(*, militar_id: int) -> str:
        return f"CTSM-{militar_id}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

    @staticmethod
    def to_dict(item: CTSMModel) -> dict:
        return {
            "id": item.id,
            "codigo": item.codigo,
            "militar_id": item.militar_id,
            "calculo_id": item.calculo_id,
            "document_id": item.document_id,
            "folha_id": item.folha_id,
            "status": item.status,
            "conteudo_json": item.conteudo_json,
            "odt_path": item.odt_path,
            "pdf_path": item.pdf_path,
            "emitido_em": item.emitido_em.isoformat() if item.emitido_em else None,
            "emitido_por_user_id": item.emitido_por_user_id,
            "observacoes": item.observacoes,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }
