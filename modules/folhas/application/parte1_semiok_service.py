from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from scripts.complete_folha_semi_ok_parte1 import (
    PairItem,
    pdf_key,
    process_pair,
    sha256_file,
)


@dataclass(slots=True)
class Parte1SemiOkPackage:
    status: str
    output_dir: Path
    package_path: Path
    package_filename: str
    manifest_path: Path
    output_odt: Path
    warnings: list[str]
    errors: list[str]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _safe_stem(value: str) -> str:
    stem = Path(value).stem
    stem = re.sub(r"[^A-Za-z0-9_. -]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" ._-")
    return stem or "folha_alteracoes"


def _find_optional_trace(output_dir: Path) -> Path | None:
    traces = sorted(output_dir.glob("*_trace.json"))
    return traces[0] if traces else None


def _write_manifest(
    *,
    run_id: str,
    output_dir: Path,
    semestre: str,
    actor_user_id: str | None,
    semi_odt: Path,
    fonte_parte1: Path,
    result,
) -> Path:
    output_odt = Path(result.output_odt) if result.output_odt else None
    output_text = Path(result.output_text) if result.output_text else None
    output_validation = Path(result.output_validation) if result.output_validation else None
    trace_path = _find_optional_trace(output_dir)
    files: list[dict] = [
        {
            "role": "INPUT_ODT_SEMI_PRONTO",
            "filename": semi_odt.name,
            "path": str(semi_odt),
            "sha256": sha256_file(semi_odt),
        },
        {
            "role": "INPUT_PARTE1_TXT" if fonte_parte1.suffix.lower() == ".txt" else "INPUT_PARTE1_PDF",
            "filename": fonte_parte1.name,
            "path": str(fonte_parte1),
            "sha256": sha256_file(fonte_parte1),
        },
    ]
    for role, path in (
        ("OUTPUT_FOLHA_ODT", output_odt),
        ("OUTPUT_PARTE1_TXT", output_text),
        ("OUTPUT_VALIDACAO_JSON", output_validation),
        ("OUTPUT_TRACE_JSON", trace_path),
    ):
        if path and path.exists():
            files.append(
                {
                    "role": role,
                    "filename": path.name,
                    "path": str(path),
                    "sha256": sha256_file(path),
                }
            )

    payload = {
        "schema_version": "sisges-folhas-semiok-parte1-upload-v1",
        "run_id": run_id,
        "generated_at": _now_iso(),
        "semestre": str(semestre),
        "actor_user_id": actor_user_id,
        "status": result.status,
        "key": result.key,
        "inserted_lines": result.inserted_lines,
        "blank_paragraphs_removed_between_parts": result.blank_paragraphs_removed_between_parts,
        "warnings": result.warnings,
        "errors": result.errors,
        "files": files,
        "operational_note": (
            "Geracao feita no modulo Folhas de Alteracoes, fora do Compilador. "
            "A conferencia visual permanece obrigatoria antes de assinatura."
        ),
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest_path


def _write_readme(output_dir: Path, result, manifest_path: Path) -> Path:
    readme_path = output_dir / "README_GERACAO_PARTE1.txt"
    lines = [
        "SISGES - Geracao de Folha de Alteracoes a partir de ODT semi-pronto",
        "",
        f"Status: {result.status}",
        f"Linhas inseridas na 1a Parte: {result.inserted_lines}",
        f"Manifesto: {manifest_path.name}",
        "",
        "Conteudo do pacote:",
        "- ODT final com a 1a Parte formatada;",
        "- texto limpo da 1a Parte;",
        "- validacao JSON;",
        "- trace tecnico;",
        "- manifest.json.",
        "",
        "Conferencia humana obrigatoria:",
        "- abrir o ODT no LibreOffice;",
        "- conferir meses, titulos, referencias BI e corpo;",
        "- revisar warnings de conteudo sensivel;",
        "- nao assinar documento com erro critico.",
    ]
    if result.warnings:
        lines.extend(["", "Warnings:"])
        lines.extend(f"- {warning}" for warning in result.warnings)
    if result.errors:
        lines.extend(["", "Erros:"])
        lines.extend(f"- {error}" for error in result.errors)
    readme_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return readme_path


def _add_if_exists(archive: zipfile.ZipFile, path: Path | None, arcname: str) -> None:
    if path and path.exists() and path.is_file():
        archive.write(path, arcname)


def _create_package(output_dir: Path, result, manifest_path: Path, readme_path: Path) -> Path:
    output_odt = Path(result.output_odt)
    stem = _safe_stem(output_odt.stem)
    package_path = output_dir / f"{stem}_parte1_formatada.zip"
    output_text = Path(result.output_text) if result.output_text else None
    output_validation = Path(result.output_validation) if result.output_validation else None
    trace_path = _find_optional_trace(output_dir)

    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        _add_if_exists(archive, readme_path, "README_GERACAO_PARTE1.txt")
        _add_if_exists(archive, manifest_path, "manifest.json")
        _add_if_exists(archive, output_odt, f"ODT_FINAL/{output_odt.name}")
        _add_if_exists(archive, output_text, f"EVIDENCIAS/{output_text.name}" if output_text else "")
        _add_if_exists(
            archive,
            output_validation,
            f"EVIDENCIAS/{output_validation.name}" if output_validation else "",
        )
        _add_if_exists(archive, trace_path, f"EVIDENCIAS/{trace_path.name}" if trace_path else "")
    return package_path


def generate_parte1_from_semiok_uploads(
    *,
    semi_odt: Path,
    fonte_parte1: Path,
    output_root: Path,
    semestre: str,
    actor_user_id: str | None,
    run_id: str | None = None,
) -> Parte1SemiOkPackage:
    run_id = run_id or uuid4().hex
    output_dir = output_root / "folhas_geracao" / "parte1_uploads" / run_id / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    key = pdf_key(fonte_parte1) or _safe_stem(semi_odt.name).lower()
    result = process_pair(
        PairItem(key=key, odt=semi_odt, pdf=fonte_parte1),
        output_dir,
        str(semestre),
        output_name_mode="militar",
    )
    if result.status == "ERROR" or not result.output_odt or not Path(result.output_odt).exists():
        manifest_path = _write_manifest(
            run_id=run_id,
            output_dir=output_dir,
            semestre=semestre,
            actor_user_id=actor_user_id,
            semi_odt=semi_odt,
            fonte_parte1=fonte_parte1,
            result=result,
        )
        _write_readme(output_dir, result, manifest_path)
        raise ValueError("; ".join(result.errors) or "Falha ao gerar ODT final.")

    manifest_path = _write_manifest(
        run_id=run_id,
        output_dir=output_dir,
        semestre=semestre,
        actor_user_id=actor_user_id,
        semi_odt=semi_odt,
        fonte_parte1=fonte_parte1,
        result=result,
    )
    readme_path = _write_readme(output_dir, result, manifest_path)
    package_path = _create_package(output_dir, result, manifest_path, readme_path)

    return Parte1SemiOkPackage(
        status=result.status,
        output_dir=output_dir,
        package_path=package_path,
        package_filename=package_path.name,
        manifest_path=manifest_path,
        output_odt=Path(result.output_odt),
        warnings=list(result.warnings),
        errors=list(result.errors),
    )
