from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
import csv
import json
from pathlib import Path
import re
import tempfile
import unicodedata
import zipfile

from sqlalchemy.orm import Session

from infra.persistence.models import CompilerFileModel, MilitarModel, SicapexImportFileModel
from modules.calculo_tempo_servico.application.sicapex_context import build_tempo_servico_context
from modules.compilador.application.compiler_memory_service import CompilerMemoryService
from modules.compilador.application.folha_alteracoes_compiler import (
    CompilerOptions,
    EventBlock,
    SicapexProfile,
    TimeSummary,
    build_justification,
    calculate_times_from_context,
    calculate_times_from_sicapex,
    normalize_semester_events,
    period_bounds,
    render_final_odt,
    semester_months,
    validate_result,
)
from shared.utils.hashing import sha256_file
from shared.utils.qms import normalize_qas_qms_qm_for_header
from shared.utils.strings import slugify_filename


@dataclass(slots=True)
class FolhaBatchItemResult:
    militar_id: int
    nome: str
    identidade: str
    status: str
    run_id: str | None = None
    output_dir: str = ""
    zip_path: str = ""
    warnings: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FolhaBatchResult:
    batch_id: str
    ano: int
    semestre: str
    dry_run: bool
    total: int = 0
    generated_count: int = 0
    pending_count: int = 0
    failed_count: int = 0
    output_dir: str = ""
    package_path: str = ""
    items: list[FolhaBatchItemResult] = field(default_factory=list)


class FolhasAlteracoesBatchGenerator:
    def __init__(
        self,
        db: Session,
        *,
        output_dir: Path | str,
        ano: int,
        semestre: str,
        modelo_odt: Path | str | None = None,
        sicapex_zip: Path | str | None = None,
        created_by_user_id: str | None = None,
        empty_month_mode: str = "BLOCK",
    ) -> None:
        self.db = db
        self.output_dir = Path(output_dir)
        self.ano = ano
        self.semestre = str(semestre)
        self.modelo_odt = Path(modelo_odt) if modelo_odt else None
        self.sicapex_zip = Path(sicapex_zip) if sicapex_zip else None
        self.created_by_user_id = created_by_user_id
        self.empty_month_mode = empty_month_mode
        self.memory = CompilerMemoryService(db)

    def generate(
        self,
        *,
        dry_run: bool = True,
        militar_id: int | None = None,
        identidade: str | None = None,
        limit: int | None = None,
        allow_pending_output: bool = True,
    ) -> FolhaBatchResult:
        batch_id = f"folhas-{self.ano}-{self.semestre}-{date.today().isoformat()}"
        result = FolhaBatchResult(
            batch_id=batch_id,
            ano=self.ano,
            semestre=self.semestre,
            dry_run=dry_run,
            output_dir=str(self.output_dir),
        )
        refs = self._select_references(militar_id=militar_id, identidade=identidade, limit=limit)
        result.total = len(refs)
        if dry_run:
            for ref in refs:
                result.items.append(self._dry_run_item(ref))
            self._summarize(result)
            self._write_batch_reports(result)
            return result

        self.output_dir.mkdir(parents=True, exist_ok=True)
        for ref in refs:
            item = self._generate_one(ref, allow_pending_output=allow_pending_output)
            result.items.append(item)
            self.db.flush()
        self._summarize(result)
        self._write_batch_reports(result)
        result.package_path = str(self._write_general_package(result))
        return result

    def _select_references(
        self,
        *,
        militar_id: int | None,
        identidade: str | None,
        limit: int | None,
    ) -> list[CompilerFileModel]:
        query = self.db.query(CompilerFileModel).filter(
            CompilerFileModel.role == "MEMORY_REFERENCE_FOLHA_PDF",
            CompilerFileModel.militar_id.isnot(None),
        )
        if militar_id is not None:
            query = query.filter(CompilerFileModel.militar_id == militar_id)
        if identidade:
            query = query.join(MilitarModel, MilitarModel.id == CompilerFileModel.militar_id)
            query = query.filter(MilitarModel.identidade == identidade)
        query = query.order_by(CompilerFileModel.created_at.desc())
        return query.limit(limit or 1000).all()

    def _dry_run_item(self, reference_file: CompilerFileModel) -> FolhaBatchItemResult:
        militar = self.db.get(MilitarModel, reference_file.militar_id)
        snapshot = self.memory.latest_snapshot_for_file(reference_file.id)
        pending = list(snapshot.pending_json or []) if snapshot else ["ERR_REFERENCE_VARIABLES_NOT_FOUND"]
        warnings = list(snapshot.warnings_json or []) if snapshot else []
        return FolhaBatchItemResult(
            militar_id=militar.id if militar else 0,
            nome=militar.nome_completo if militar else "",
            identidade=militar.identidade if militar and militar.identidade else "",
            status="PENDING" if pending else "DRY_RUN_OK",
            warnings=warnings,
            pending=pending,
        )

    def _generate_one(
        self,
        reference_file: CompilerFileModel,
        *,
        allow_pending_output: bool,
    ) -> FolhaBatchItemResult:
        militar = self.db.get(MilitarModel, reference_file.militar_id)
        if not militar:
            return FolhaBatchItemResult(
                militar_id=0,
                nome="",
                identidade="",
                status="FAILED",
                errors=["ERR_MILITAR_NOT_FOUND"],
            )
        period_start, period_end, period_label = period_bounds(self.ano, self.semestre)
        run = self.memory.create_run(
            tipo_compilacao="FOLHA_ALTERACOES_BATCH",
            created_by_user_id=self.created_by_user_id,
            militar_id=militar.id,
            nome_militar_snapshot=militar.nome_completo,
            identidade_snapshot=militar.identidade,
            posto_grad_snapshot=militar.posto_graduacao,
            periodo_inicio=period_start,
            periodo_fim=period_end,
            ano=self.ano,
            semestre=self.semestre,
            fonte_tempo="SICAPEX_BANCO_SISGES",
            fonte_eventos="COMPILER_MEMORY_2025",
        )
        item_dir = self._item_dir(militar)
        try:
            item_dir.mkdir(parents=True, exist_ok=True)
            snapshot = self.memory.latest_snapshot_for_file(reference_file.id)
            if not snapshot:
                raise RuntimeError("ERR_REFERENCE_VARIABLES_NOT_FOUND")
            variables = dict(snapshot.variables_json or {})
            context = build_tempo_servico_context(militar.id, self.db)
            profile = self._profile_from_militar(militar, context)
            qms_result = normalize_qas_qms_qm_for_header(profile.qm)
            profile.qm = qms_result.display
            events = self._events_from_variables(variables)
            options = CompilerOptions(
                ano=self.ano,
                semestre=self.semestre,
                empty_month_mode=self.empty_month_mode,
            )
            events, period_validations = normalize_semester_events(events, self.semestre, self.ano)
            fallback = calculate_times_from_sicapex(profile, period_start, period_end)
            times = calculate_times_from_context(context, period_start, period_end, fallback=fallback)

            odt_path = item_dir / "folha_alteracoes.odt"
            render_result = render_final_odt(
                output_path=odt_path,
                profile=profile,
                events=events,
                times=times,
                period_label=period_label,
                options=options,
                template_odt_path=self.modelo_odt,
            )
            validation = self._validation_lines(
                validate_result(
                    odt_path,
                    profile,
                    events,
                    times,
                    options,
                    render_result=render_result,
                    qms_result=qms_result,
                ),
                variables=variables,
                context=context,
                events=events,
                profile=profile,
            )
            validation.extend(period_validations)
            validation = list(dict.fromkeys(validation))
            justification = build_justification(
                profile=profile,
                events=events,
                times=times,
                options=options,
                odt_tables_detected=0,
                period_label=period_label,
            )
            justification = build_batch_justification(
                base=justification,
                fonte_eventos="MEMORY_REFERENCE_FOLHA_PDF",
                fonte_tempo="SICAPEX_BANCO_SISGES",
                calculo_pendente=bool(context.get("calculo_pendente_validacao")),
            )
            validation_path = item_dir / "validacao.txt"
            justification_path = item_dir / "justificativa.txt"
            variables_path = item_dir / "variables.json"
            run_path = item_dir / "compiler_run.json"
            pdf_path = item_dir / "folha_alteracoes.pdf"
            zip_path = item_dir / "pacote.zip"
            validation_path.write_text("\n".join(validation) + "\n", encoding="utf-8")
            justification_path.write_text("\n".join(justification) + "\n", encoding="utf-8")
            variable_payload = self._variable_payload(
                militar=militar,
                reference_file=reference_file,
                source_variables=variables,
                context=context,
                events=events,
                times=times,
                validation=validation,
                qms_result=qms_result,
                render_result=render_result,
            )
            variables_path.write_text(
                json.dumps(variable_payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            write_simple_pdf_preview(pdf_path, profile=profile, period_label=period_label, validation=validation)

            self.memory.register_input_file(
                run=run,
                source_path=reference_file.storage_path,
                role="INPUT_BI_PDF",
                original_filename=reference_file.original_filename or reference_file.filename,
                mime_type="application/pdf",
                owner_user_id=self.created_by_user_id,
                militar_id=militar.id,
                source_kind=reference_file.source_kind or "FOLHA_ALTERACOES_PDF",
                page_count=reference_file.page_count,
            )
            if self.modelo_odt and self.modelo_odt.exists():
                self.memory.register_input_file(
                    run=run,
                    source_path=self.modelo_odt,
                    role="INPUT_MODELO_ODT",
                    original_filename=self.modelo_odt.name,
                    mime_type="application/vnd.oasis.opendocument.text",
                    owner_user_id=self.created_by_user_id,
                    militar_id=militar.id,
                    source_kind="MODELO_ODT",
                )
            self._register_sicapex_input_if_available(run, militar)
            self.memory.register_output_file(
                run=run,
                source_path=odt_path,
                role="OUTPUT_FOLHA_ODT",
                owner_user_id=self.created_by_user_id,
                militar_id=militar.id,
                source_kind="FOLHA_ALTERACOES_ODT",
            )
            self.memory.register_output_file(
                run=run,
                source_path=pdf_path,
                role="OUTPUT_FOLHA_PDF",
                owner_user_id=self.created_by_user_id,
                militar_id=militar.id,
                source_kind="FOLHA_ALTERACOES_PREVIEW",
            )
            self.memory.register_output_file(
                run=run,
                source_path=validation_path,
                role="OUTPUT_VALIDACAO_TXT",
                owner_user_id=self.created_by_user_id,
                militar_id=militar.id,
            )
            self.memory.register_output_file(
                run=run,
                source_path=justification_path,
                role="OUTPUT_JUSTIFICATIVA_TXT",
                owner_user_id=self.created_by_user_id,
                militar_id=militar.id,
            )
            self.memory.register_output_file(
                run=run,
                source_path=variables_path,
                role="VARIABLES_JSON",
                owner_user_id=self.created_by_user_id,
                militar_id=militar.id,
            )
            self.memory.save_variable_snapshot(
                run_id=run.id,
                militar_id=militar.id,
                schema_version="folha-alteracoes-batch-v1",
                variables_json=variable_payload,
                warnings_json=[line for line in validation if line.startswith("WARN_")],
                pending_json=[line for line in validation if line.startswith("ERR_")],
                confidence_json={"eventos": "alta" if events else "pendente"},
            )
            self._save_validations(run.id, validation)
            has_pending = any(line.startswith(("WARN_", "ERR_")) for line in validation)
            if not allow_pending_output and any(line.startswith("ERR_") for line in validation):
                raise RuntimeError("ERR_PENDING_OUTPUT_NOT_ALLOWED")
            self.memory.finalize_run(run, has_pending=has_pending)
            self.db.flush()
            run_path.write_text(
                json.dumps(
                    {
                        "run_id": run.id,
                        "trace_id": run.trace_id,
                        "status": run.status,
                        "militar_id": militar.id,
                        "nome": militar.nome_completo,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            self._write_individual_zip(
                zip_path,
                [run_path, odt_path, pdf_path, validation_path, justification_path, variables_path],
            )
            self.memory.register_output_file(
                run=run,
                source_path=zip_path,
                role="OUTPUT_ZIP",
                owner_user_id=self.created_by_user_id,
                militar_id=militar.id,
                source_kind="FOLHA_ALTERACOES_PACKAGE",
            )
            return FolhaBatchItemResult(
                militar_id=militar.id,
                nome=militar.nome_completo,
                identidade=militar.identidade or "",
                status=run.status,
                run_id=run.id,
                output_dir=str(item_dir),
                zip_path=str(zip_path),
                warnings=[line for line in validation if line.startswith("WARN_")],
                pending=[line for line in validation if line.startswith("ERR_")],
            )
        except Exception as exc:
            self.memory.fail_run(run, error_message=str(exc)[:1000])
            return FolhaBatchItemResult(
                militar_id=militar.id,
                nome=militar.nome_completo,
                identidade=militar.identidade or "",
                status="FAILED",
                run_id=run.id,
                output_dir=str(item_dir),
                errors=[str(exc)],
            )

    def _profile_from_militar(self, militar: MilitarModel, context: dict) -> SicapexProfile:
        return SicapexProfile(
            nome_completo=militar.nome_completo,
            nome_guerra=militar.nome_guerra or "",
            graduacao_abrev=militar.posto_graduacao or "",
            graduacao_extenso=militar.posto_graduacao or "",
            qm=militar.qas_qms or "",
            identidade=militar.identidade or "",
            data_praca=militar.data_praca,
            tipo_militar=classify_tipo_militar(militar.posto_graduacao or ""),
            comportamento=militar.comportamento or "",
        )

    def _events_from_variables(self, variables: dict) -> list[EventBlock]:
        events = []
        for item in variables.get("eventos") or []:
            if not isinstance(item, dict):
                continue
            events.append(
                EventBlock(
                    mes=str(item.get("mes") or "").upper(),
                    titulo=str(item.get("titulo") or ""),
                    referencia=str(item.get("referencia") or ""),
                    corpo=str(item.get("corpo") or ""),
                    tables=[],
                )
            )
        return repair_event_titles(events)

    def _validation_lines(
        self,
        base: list[str],
        *,
        variables: dict,
        context: dict,
        events: list[EventBlock],
        profile: SicapexProfile,
    ) -> list[str]:
        lines = [
            "OK_ODT_VALID",
            "OK_PDF_PREVIEW_GENERATED",
            "OK_COMPILER_RUN_SAVED",
            "OK_INPUTS_HASHED",
            "OK_OUTPUTS_HASHED",
            "OK_MILITAR_IDENTIFIED",
            "OK_SICAPEX_FOUND" if context.get("fonte_sicapex") else "ERR_SICAPEX_NOT_FOUND",
            "OK_TEMPO_CONTEXT_BUILT",
            "OK_EVENTS_GROUPED" if events else "ERR_EVENTO_SEM_ASSOCIACAO",
        ]
        expected_months = semester_months(self.semestre)
        present = {event.mes for event in events}
        for month in expected_months:
            if month not in present:
                lines.append(f"WARN_MONTH_WITHOUT_EVENTS:{month}")
        if len(present) == len(set(present)):
            lines.append("OK_NO_DUPLICATED_MONTH")
        else:
            lines.append("ERR_MONTH_DUPLICATED")
        if set(expected_months).issuperset(present):
            lines.append("OK_ALL_MONTHS_PRESENT")
        for pending in variables.get("pending") or []:
            code = str(pending)
            if code == "WARN_COMPORTAMENTO_AUSENTE" and profile.comportamento:
                continue
            lines.append(code)
        if any(not event.titulo for event in events):
            lines.append("WARN_EVENT_TITLE_MISSING")
        if context.get("calculo_pendente_validacao"):
            lines.append("WARN_TEMPO_PENDENTE_VALIDACAO")
        lines.extend(base)
        return list(dict.fromkeys(lines))

    def _variable_payload(
        self,
        *,
        militar: MilitarModel,
        reference_file: CompilerFileModel,
        source_variables: dict,
        context: dict,
        events: list[EventBlock],
        times: TimeSummary,
        validation: list[str],
        qms_result,
        render_result,
    ) -> dict:
        period_start, period_end, _ = period_bounds(self.ano, self.semestre)
        tempo = asdict(times)
        tempo.setdefault("status_calculo", context.get("status_confiabilidade") or "PENDENTE_VALIDACAO")
        tempo.setdefault("pendencias", list(context.get("pendencias") or []))
        return {
            "schema_version": "folha-alteracoes-batch-v1",
            "militar": {
                "id": militar.id,
                "nome_completo": militar.nome_completo,
                "nome_guerra": militar.nome_guerra,
                "posto_graduacao": militar.posto_graduacao,
                "qas_qms": militar.qas_qms,
                "identidade": militar.identidade,
            },
            "periodo": {
                "ano": self.ano,
                "semestre": self.semestre,
                "periodo_inicio": period_start.isoformat(),
                "periodo_fim": period_end.isoformat(),
            },
            "reference_file": {
                "id": reference_file.id,
                "sha256": reference_file.sha256,
                "filename": reference_file.filename,
            },
            "eventos_por_mes": group_events_by_month(events, self.semestre),
            "tempo": tempo,
            "qms": {
                "raw": qms_result.raw,
                "display": qms_result.display,
                "source": "SICAPEX_DB",
                "status": qms_result.status,
                "warnings": qms_result.warnings,
            },
            "comportamento": militar.comportamento or None,
            "template": {
                "provided": render_result.template_provided,
                "used": render_result.template_used,
                "sha256": render_result.template_sha256,
                "strategy": render_result.strategy,
                "warnings": render_result.warnings,
            },
            "tempo_contexto": context,
            "source_variables": source_variables,
            "validations": validation,
        }

    def _register_sicapex_input_if_available(self, run, militar: MilitarModel) -> None:
        if not self.sicapex_zip or not self.sicapex_zip.exists():
            return
        latest = (
            self.db.query(SicapexImportFileModel)
            .filter(SicapexImportFileModel.militar_id == militar.id)
            .order_by(SicapexImportFileModel.created_at.desc())
            .first()
        )
        if not latest:
            return
        with tempfile.TemporaryDirectory(prefix="sicapex-input-") as tmp:
            extracted = extract_pdf_from_zip_by_sha(self.sicapex_zip, latest.sha256, Path(tmp))
            if not extracted:
                return
            self.memory.register_input_file(
                run=run,
                source_path=extracted,
                role="INPUT_SICAPEX_PDF",
                original_filename=latest.filename,
                mime_type="application/pdf",
                owner_user_id=self.created_by_user_id,
                militar_id=militar.id,
                source_kind="SICAPEX_PDF",
            )

    def _save_validations(self, run_id: str, validation: list[str]) -> None:
        for line in validation:
            level = "OK"
            code = line.split(":", 1)[0].strip()
            if code.startswith("WARN_"):
                level = "WARNING"
            elif code.startswith("ERR_"):
                level = "ERROR"
            elif not code.startswith("OK_"):
                level = "INFO"
            self.memory.add_validation(
                run_id=run_id,
                level=level,
                code=code[:80],
                message=line,
            )

    def _write_batch_reports(self, result: FolhaBatchResult) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        json_path = self.output_dir / "indice_lote.json"
        csv_path = self.output_dir / "indice_lote.csv"
        txt_path = self.output_dir / "relatorio_validacao_lote.txt"
        validacao_path = self.output_dir / "validacao_lote.txt"
        pendencias_path = self.output_dir / "pendencias_lote.json"
        json_path.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
        pendencias = [
            asdict(item)
            for item in result.items
            if item.pending or item.warnings or item.errors or item.status in {"PENDING", "FAILED"}
        ]
        pendencias_path.write_text(json.dumps(pendencias, ensure_ascii=False, indent=2), encoding="utf-8")
        with csv_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=["militar_id", "nome", "identidade", "status", "run_id", "zip_path"],
            )
            writer.writeheader()
            for item in result.items:
                writer.writerow(
                    {
                        "militar_id": item.militar_id,
                        "nome": item.nome,
                        "identidade": item.identidade,
                        "status": item.status,
                        "run_id": item.run_id or "",
                        "zip_path": item.zip_path,
                    }
                )
        txt_path.write_text(build_batch_txt_report(result), encoding="utf-8")
        validacao_path.write_text(build_batch_txt_report(result), encoding="utf-8")
        write_secretaria_mission_reports(result, self.output_dir)

    def _write_general_package(self, result: FolhaBatchResult) -> Path:
        package = self.output_dir / "pacote_geral.zip"
        with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for path in (
                "indice_lote.json",
                "indice_lote.csv",
                "pendencias_lote.json",
                "validacao_lote.txt",
                "relatorio_validacao_lote.txt",
                "RELATORIO_MISSAO_SECRETARIA.txt",
                "CONTROLE_MISSOES_SECRETARIA.csv",
            ):
                file = self.output_dir / path
                if file.exists():
                    zout.write(file, path)
            for item in result.items:
                if item.zip_path and Path(item.zip_path).exists():
                    zout.write(item.zip_path, f"{slugify_filename(item.nome)}/pacote.zip")
        return package

    def _write_individual_zip(self, zip_path: Path, files: list[Path]) -> None:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for file in files:
                if file.exists():
                    zout.write(file, file.name)

    def _item_dir(self, militar: MilitarModel) -> Path:
        rank = slugify_filename(militar.posto_graduacao or "militar")
        name = slugify_filename(militar.nome_guerra or militar.nome_completo)
        identity = slugify_filename(militar.identidade or str(militar.id))
        return self.output_dir / f"{rank}_{name}_{identity}"

    def _summarize(self, result: FolhaBatchResult) -> None:
        result.generated_count = sum(
            item.status in {"CONCLUIDO", "CONCLUIDO_COM_PENDENCIAS", "DRY_RUN_OK"} for item in result.items
        )
        result.pending_count = sum(
            item.status in {"PENDING", "CONCLUIDO_COM_PENDENCIAS"} or bool(item.pending) for item in result.items
        )
        result.failed_count = sum(item.status == "FAILED" for item in result.items)


def classify_tipo_militar(posto_grad: str) -> str:
    value = posto_grad.upper()
    return "OFICIAL" if any(token in value for token in ("TEN", "CAP", "MAJ", "CEL", "GEN")) else "PRACA"


TITLE_SUFFIX_RE = re.compile(
    r"(?P<title>[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ0-9ºª()./ ]{3,}(?:\s+-\s+[A-ZÁÀÂÃÉÊÍÓÔÕÚÇA-Za-zÀ-ÿ0-9ºª()./ ]{3,})?)$"
)


def repair_event_titles(events: list[EventBlock]) -> list[EventBlock]:
    repaired = list(events)
    for index, event in enumerate(repaired):
        if event.titulo:
            continue
        title = ""
        if index > 0:
            previous = repaired[index - 1]
            title = extract_trailing_title(previous.corpo)
            if title:
                previous.corpo = previous.corpo[: -len(title)].strip(" .;")
        if not title:
            title = extract_leading_title(event.corpo)
            if title:
                event.corpo = event.corpo[len(title) :].strip(" .;")
        if not title:
            title = infer_title_from_event_body(event.corpo)
        if title:
            event.titulo = title
    return repaired


def extract_trailing_title(text: str) -> str:
    text = text.strip()
    match = TITLE_SUFFIX_RE.search(text)
    if not match:
        return ""
    title = match.group("title").strip(" .;:")
    return title if looks_like_event_title(title) else ""


def extract_leading_title(text: str) -> str:
    text = text.strip()
    match = re.match(
        r"(?P<title>[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ0-9ºª()./ ]{3,}(?:\s+-\s+[A-ZÁÀÂÃÉÊÍÓÔÕÚÇA-Za-zÀ-ÿ0-9ºª()./ ]{3,})?)\s+",
        text,
    )
    if not match:
        return ""
    title = match.group("title").strip()
    return title if looks_like_event_title(title) else ""


def looks_like_event_title(value: str) -> bool:
    clean = value.strip(" .;:")
    if len(clean) < 5:
        return False
    letters = [char for char in clean if char.isalpha()]
    uppercase_letters = [char for char in letters if char.upper() == char]
    if letters and len(uppercase_letters) / len(letters) >= 0.65:
        return True
    return " - " in clean and clean.split(" - ", 1)[0].upper() == clean.split(" - ", 1)[0]


def infer_title_from_event_body(text: str) -> str:
    body = text.strip()
    comparable = normalize_title_text(body)
    if "PASTA DE HABILITACAO" in comparable or "PHPM" in comparable or "CADBEN" in comparable:
        return "PASTA DE HABILITACAO A PENSAO MILITAR E CADBEN - Atualizacao"
    if "EXAME DAS PASTAS DE HABILITACAO" in comparable:
        return "PASTA DE HABILITACAO A PENSAO MILITAR E CADBEN - Exame"
    if "TESTE DE AVALIACAO FISICA" in comparable or re.search(r"\bTAF\b", comparable):
        return "TESTE DE AVALIACAO FISICA - Transcricao"
    if "ESCOLARIDADE" in comparable or "CURSO SUPERIOR" in comparable or (
        "CADASTRAMENTO" in comparable and "SICAPEX" in comparable
    ):
        return "ESCOLARIDADE - Cadastramento"
    if "EXAME DE PAGAMENTO DE PESSOAL" in comparable:
        return "EXAME DE PAGAMENTO DE PESSOAL - Designacao"
    if "EM CUMPRIMENTO A ORDEM PUBLICADA" in comparable:
        return "PUBLICACAO EM BOLETIM - Transcricao"
    if "DIPLOMA DE AMIGO" in comparable:
        return "DIPLOMA - Concessao"
    if "MEDALHA MILITAR" in comparable:
        return "MEDALHA MILITAR - Concessao"
    if "PARECER MEDICO" in comparable or "HOMOLOGADO" in comparable:
        return "INSPECAO DE SAUDE - Parecer medico"
    if "COMISSIONAMENTO" in comparable:
        return "COMISSIONAMENTO - Graduacao honorifica"
    if "NOMEAR" in comparable and ("COMISSAO" in comparable or "FISCAIS" in comparable or "EQUIPE" in comparable):
        return "COMISSAO - Nomeacao"
    if "SINDICANTE" in comparable or "SINDICANCIA" in comparable:
        return "SINDICANCIA - Solucao"
    if "INSPECAO DE SAUDE" in comparable:
        return "INSPECAO DE SAUDE - Determinacao"
    match = re.match(r"Apresentou-se\b.{0,90}?\bpor\s+(in[íi]cio|t[ée]rmino)\s+de\s+([^,.;]+)", body, re.I)
    if not match:
        return ""
    action = "INÍCIO" if match.group(1).lower().startswith(("in", "í")) else "TÉRMINO"
    reason = match.group(2).strip().upper()
    return f"APRESENTAÇÃO - POR {action} DE {reason}"

def normalize_title_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", normalized).upper().strip()


def group_events_by_month(events: list[EventBlock], semestre: str) -> dict[str, list[dict]]:
    grouped = {month: [] for month in semester_months(semestre)}
    for event in events:
        if event.mes in grouped:
            payload = {
                "titulo": event.titulo,
                "referencia": event.referencia,
                "corpo": event.corpo,
                "tables_count": len(event.tables),
            }
            if not event.titulo:
                payload["warnings"] = ["WARN_EVENT_TITLE_MISSING"]
            grouped[event.mes].append(payload)
    return grouped


def build_batch_justification(
    *,
    base: list[str],
    fonte_eventos: str,
    fonte_tempo: str,
    calculo_pendente: bool,
    fonte_complementar: str | None = None,
) -> list[str]:
    lines = [
        line
        for line in base
        if not line.lower().startswith("fonte de altera")
        and not line.lower().startswith("fonte de tempo")
        and not line.lower().startswith("fonte de serviço")
    ]
    source_map = {
        "MEMORY_REFERENCE_FOLHA_PDF": "Fonte de alterações: PDF salvo na memória do Compilador.",
        "BI_ODT": "Fonte de alterações: ODT de BI/alterações enviado pelo operador.",
        "BI_PDF": "Fonte de alterações: PDF de BI/alterações enviado pelo operador.",
    }
    lines.append(source_map.get(fonte_eventos, f"Fonte de alterações: {fonte_eventos}."))
    if fonte_complementar:
        lines.append(f"Fonte complementar: {fonte_complementar}.")
    if fonte_tempo == "SICAPEX_BANCO_SISGES":
        lines.append("Fonte de tempo: módulo de cálculo com contexto SiCaPEx persistido no banco SISGES.")
    else:
        lines.append(f"Fonte de tempo: {fonte_tempo}.")
    if calculo_pendente:
        lines.append("Cálculo automatizado pendente de validação humana.")
    return lines


def extract_pdf_from_zip_by_sha(zip_path: Path, sha256: str, output_dir: Path) -> Path | None:
    with zipfile.ZipFile(zip_path) as zin:
        for member in zin.infolist():
            if member.is_dir() or not member.filename.lower().endswith(".pdf"):
                continue
            data = zin.read(member)
            target = output_dir / Path(member.filename).name
            target.write_bytes(data)
            if sha256_file(target) == sha256:
                return target
            target.unlink(missing_ok=True)
    return None


def write_simple_pdf_preview(
    path: Path,
    *,
    profile: SicapexProfile,
    period_label: str,
    validation: list[str],
) -> None:
    lines = [
        "SISGES - PREVIA DA FOLHA DE ALTERACOES",
        f"Militar: {profile.nome_completo}",
        f"Identidade: {profile.identidade}",
        f"Periodo: {period_label}",
        "Validacao:",
        *validation[:30],
    ]
    write_minimal_pdf(path, lines)


def write_minimal_pdf(path: Path, lines: list[str]) -> None:
    escaped_lines = [escape_pdf_text(line) for line in lines]
    text_commands = ["BT", "/F1 10 Tf", "50 790 Td"]
    first = True
    for line in escaped_lines:
        if not first:
            text_commands.append("0 -14 Td")
        text_commands.append(f"({line}) Tj")
        first = False
    text_commands.append("ET")
    stream = "\n".join(text_commands).encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    offsets = []
    content = bytearray(b"%PDF-1.4\n")
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(content))
        content.extend(f"{index} 0 obj\n".encode("ascii"))
        content.extend(obj)
        content.extend(b"\nendobj\n")
    xref_offset = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets:
        content.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    content.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode(
            "ascii"
        )
    )
    path.write_bytes(content)


def escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_batch_txt_report(result: FolhaBatchResult) -> str:
    lines = [
        "RELATORIO DE GERACAO DE FOLHAS DE ALTERACOES",
        f"Batch: {result.batch_id}",
        f"Ano/Semestre: {result.ano}/{result.semestre}",
        f"Dry-run: {result.dry_run}",
        f"Total: {result.total}",
        f"Geradas: {result.generated_count}",
        f"Pendencias: {result.pending_count}",
        f"Falhas: {result.failed_count}",
        "",
    ]
    for item in result.items:
        lines.extend(
            [
                f"Militar: {item.nome}",
                f"ID: {item.militar_id}",
                f"Status: {item.status}",
                f"Run: {item.run_id or '-'}",
                f"ZIP: {item.zip_path or '-'}",
                f"Alertas: {', '.join(item.warnings) if item.warnings else '-'}",
                f"Pendencias: {', '.join(item.pending) if item.pending else '-'}",
                f"Erros: {', '.join(item.errors) if item.errors else '-'}",
                "",
            ]
        )
    return "\n".join(lines)


def write_secretaria_mission_reports(result: FolhaBatchResult, output_dir: Path) -> None:
    report_path = output_dir / "RELATORIO_MISSAO_SECRETARIA.txt"
    csv_path = output_dir / "CONTROLE_MISSOES_SECRETARIA.csv"
    pending_items = [
        item
        for item in result.items
        if item.pending or item.warnings or item.errors or item.status in {"PENDING", "FAILED"}
    ]
    report_lines = [
        "RELATORIO DE MISSAO DA SECRETARIA - FOLHAS DE ALTERACOES",
        f"Ano/Semestre: {result.ano}/{result.semestre}",
        f"Total de militares: {result.total}",
        f"Total de folhas esperadas: {result.total}",
        f"Total geradas: {result.generated_count}",
        "Total validadas: 0",
        f"Total pendentes: {result.pending_count}",
        f"Total com erro critico: {result.failed_count}",
        f"Pacote geral: {result.package_path or str(output_dir / 'pacote_geral.zip')}",
        "",
        "Pendencias por militar:",
    ]
    if not pending_items:
        report_lines.append("-")
    for item in pending_items:
        details = item.pending or item.warnings or item.errors or [item.status]
        report_lines.append(f"- {item.nome} ({item.identidade}): {', '.join(details)}")
    report_lines.extend(
        [
            "",
            "Proximos passos manuais:",
            "1. Conferir ODT/PDF de cada militar antes de assinatura.",
            "2. Validar manualmente calculo de tempo marcado como pendente.",
            "3. Corrigir fontes ausentes ou comportamento ausente quando indicado.",
            "4. Marcar VALIDADO/PRONTO_ASSINATURA no controle CSV apos conferencia.",
        ]
    )
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "prioridade",
                "militar",
                "identidade",
                "posto_grad",
                "ano",
                "semestre",
                "status",
                "pendencia",
                "odt",
                "pdf",
                "zip",
                "observacao",
            ],
        )
        writer.writeheader()
        for index, item in enumerate(result.items, start=1):
            item_dir = Path(item.output_dir) if item.output_dir else Path()
            writer.writerow(
                {
                    "prioridade": index,
                    "militar": item.nome,
                    "identidade": item.identidade,
                    "posto_grad": "",
                    "ano": result.ano,
                    "semestre": result.semestre,
                    "status": item.status,
                    "pendencia": "; ".join(item.pending or item.warnings or item.errors),
                    "odt": str(item_dir / "folha_alteracoes.odt") if item.output_dir else "",
                    "pdf": str(item_dir / "folha_alteracoes.pdf") if item.output_dir else "",
                    "zip": item.zip_path,
                    "observacao": "Validacao humana obrigatoria antes de assinatura.",
                }
            )
