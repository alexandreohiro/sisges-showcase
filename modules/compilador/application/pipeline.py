from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import logging
import shutil
from time import perf_counter

from infra.odt.templates import OdtTemplateRegistry, TemplateVersion
from infra.pipeline.workspace import PipelineWorkspace
from modules.compilador.application.render_odt import RenderOdtUseCase
from modules.compilador.application.services import RealCompilerPipelineService
from modules.compilador.application.validate_compilation import validate_record
from modules.compilador.domain.entities import CompilationRecord
from modules.documents.application.services import DocumentService
from shared.utils.hashing import sha256_file
from shared.utils.strings import slugify_filename


logger = logging.getLogger("sisges.compilador.pipeline")


@dataclass(frozen=True)
class PipelineArtifact:
    path: Path
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class PipelineStep:
    name: str
    status: str
    duration_ms: int
    details: dict = field(default_factory=dict)


@dataclass
class CompilePdfPipelineResult:
    trace_id: str
    record: CompilationRecord
    input_pdf: PipelineArtifact
    steps: list[PipelineStep]


@dataclass
class RenderOdtPipelineResult:
    trace_id: str
    record: CompilationRecord
    input_pdf: PipelineArtifact | None
    template: TemplateVersion
    output: PipelineArtifact
    render_info: dict
    document_id: str | None
    download_url: str | None
    steps: list[PipelineStep]


class CompilerDocumentPipeline:
    def __init__(
        self,
        compiler: RealCompilerPipelineService,
        renderer: RenderOdtUseCase,
        template_registry: OdtTemplateRegistry | None = None,
        output_dir: str | Path = "data/outputs",
    ) -> None:
        self.compiler = compiler
        self.renderer = renderer
        self.template_registry = template_registry or OdtTemplateRegistry()
        self.output_dir = Path(output_dir)

    def compile_pdf(self, *, pdf_path: Path, workspace: PipelineWorkspace) -> CompilePdfPipelineResult:
        steps: list[PipelineStep] = []
        input_artifact = self._artifact(pdf_path)

        record = self._timed_step(
            steps,
            "extract_normalize_parse_enrich",
            lambda: self.compiler.compile_pdf(pdf_path),
            {"input_sha256": input_artifact.sha256},
        )

        diagnostics = self._timed_step(
            steps,
            "validate_compilation",
            lambda: validate_record(record),
            {"diagnostics_before": len(record.diagnostics)},
        )
        record.diagnostics.extend(diagnostics)
        record.metadata.update(
            {
                "trace_id": workspace.trace_id,
                "input_pdf_sha256": input_artifact.sha256,
                "input_pdf_size_bytes": input_artifact.size_bytes,
                "pipeline_steps": [step.__dict__ for step in steps],
            }
        )

        return CompilePdfPipelineResult(
            trace_id=workspace.trace_id,
            record=record,
            input_pdf=input_artifact,
            steps=steps,
        )

    def render_odt_from_pdf(
        self,
        *,
        pdf_path: Path,
        template_path: Path,
        template_filename: str,
        workspace: PipelineWorkspace,
        document_service: DocumentService | None = None,
        owner_user_id: str | None = None,
    ) -> RenderOdtPipelineResult:
        compile_result = self.compile_pdf(pdf_path=pdf_path, workspace=workspace)
        return self.render_odt_from_record(
            record=compile_result.record,
            template_path=template_path,
            template_filename=template_filename,
            workspace=workspace,
            input_pdf=compile_result.input_pdf,
            inherited_steps=compile_result.steps,
            document_service=document_service,
            owner_user_id=owner_user_id,
        )

    def render_odt_from_record(
        self,
        *,
        record: CompilationRecord,
        template_path: Path,
        template_filename: str,
        workspace: PipelineWorkspace,
        input_pdf: PipelineArtifact | None = None,
        inherited_steps: list[PipelineStep] | None = None,
        document_service: DocumentService | None = None,
        owner_user_id: str | None = None,
    ) -> RenderOdtPipelineResult:
        steps = list(inherited_steps or [])

        if record.pending_fields:
            raise ValueError("Existem pendencias canonicas. Resolva antes de gerar o ODT.")

        template = self._timed_step(
            steps,
            "register_template_version",
            lambda: self.template_registry.register_uploaded_template(template_path, template_filename),
            {"template_filename": template_filename},
        )

        self.output_dir.mkdir(parents=True, exist_ok=True)
        safe_name = slugify_filename(record.header.nome_completo, fallback="registro")
        output_path = self.output_dir / f"{safe_name}-{workspace.trace_id[:8]}.odt"

        render_info = self._timed_step(
            steps,
            "render_odt",
            lambda: self.renderer.execute(
                record=record,
                template_path=template.storage_path,
                output_path=workspace.output_dir / output_path.name,
            ),
            {"template_version": template.version},
        )

        workspace_output = Path(render_info["output_path"])
        shutil.move(str(workspace_output), output_path)
        output_artifact = self._artifact(output_path)
        render_info["output_path"] = str(output_path).replace("\\", "/")

        record.metadata.update(
            {
                "trace_id": workspace.trace_id,
                "template_sha256": template.sha256,
                "template_version": template.version,
                "output_sha256": output_artifact.sha256,
                "output_size_bytes": output_artifact.size_bytes,
                "pipeline_steps": [step.__dict__ for step in steps],
            }
        )

        document_id = None
        download_url = None
        if document_service is not None:
            doc = document_service.register_document(
                kind="ODT",
                filename=output_path.name,
                status="generated",
                source_module="compilador",
                output_path=str(output_path).replace("\\", "/"),
                owner_user_id=owner_user_id,
                trace_id=workspace.trace_id,
                template_sha256=template.sha256,
                template_version=template.version,
                input_sha256=input_pdf.sha256 if input_pdf else None,
                output_sha256=output_artifact.sha256,
                metadata={
                    "template_filename": template.original_filename,
                    "input_pdf_size_bytes": input_pdf.size_bytes if input_pdf else None,
                    "output_size_bytes": output_artifact.size_bytes,
                    "pipeline_steps": [step.__dict__ for step in steps],
                },
            )
            document_id = doc.id
            download_url = f"/documents/{doc.id}/download"

        return RenderOdtPipelineResult(
            trace_id=workspace.trace_id,
            record=record,
            input_pdf=input_pdf,
            template=template,
            output=output_artifact,
            render_info=render_info,
            document_id=document_id,
            download_url=download_url,
            steps=steps,
        )

    @staticmethod
    def _artifact(path: Path) -> PipelineArtifact:
        return PipelineArtifact(
            path=path,
            sha256=sha256_file(path),
            size_bytes=path.stat().st_size,
        )

    @staticmethod
    def _timed_step(
        steps: list[PipelineStep],
        name: str,
        action,
        details: dict | None = None,
    ):
        started = perf_counter()
        try:
            result = action()
        except Exception:
            duration_ms = int((perf_counter() - started) * 1000)
            steps.append(PipelineStep(name=name, status="failed", duration_ms=duration_ms))
            logger.exception("Pipeline step failed", extra={"step": name, "duration_ms": duration_ms})
            raise

        duration_ms = int((perf_counter() - started) * 1000)
        steps.append(
            PipelineStep(
                name=name,
                status="ok",
                duration_ms=duration_ms,
                details=details or {},
            )
        )
        logger.info("Pipeline step completed", extra={"step": name, "duration_ms": duration_ms})
        return result
