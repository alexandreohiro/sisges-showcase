from __future__ import annotations

import argparse
import json
from pathlib import Path

from infra.persistence.db import SessionLocal
from modules.compilador.application.compiler_reference_importer import (
    CompilerReferenceImportReport,
    CompilerReferenceImporter,
)


def report_to_dict(report: CompilerReferenceImportReport) -> dict:
    return {
        "source_folder": report.source_folder,
        "total_files": report.total_files,
        "imported_count": report.imported_count,
        "updated_count": report.updated_count,
        "duplicate_count": report.duplicate_count,
        "failed_count": report.failed_count,
        "pending_count": report.pending_count,
        "matched_militares": report.matched_militares,
        "items": [
            {
                "filename": item.filename,
                "sha256": item.sha256,
                "status": item.status,
                "file_id": item.file_id,
                "run_id": item.run_id,
                "document_id": item.document_id,
                "militar_id": item.militar_id,
                "nome": item.nome,
                "identidade_mascarada": item.identidade_mascarada,
                "ano": item.ano,
                "semestre": item.semestre,
                "eventos_count": item.eventos_count,
                "warnings": item.warnings,
                "pending": item.pending,
                "error": item.error,
            }
            for item in report.items
        ],
    }


def report_to_txt(report: CompilerReferenceImportReport) -> str:
    lines = [
        "Importacao de PDFs para Memoria do Compilador",
        f"Fonte: {report.source_folder}",
        f"Arquivos: {report.total_files}",
        f"Importados: {report.imported_count}",
        f"Atualizados: {report.updated_count}",
        f"Duplicados SHA: {report.duplicate_count}",
        f"Pendencias: {report.pending_count}",
        f"Falhas: {report.failed_count}",
        f"Vinculados a Gestao de Pessoal: {report.matched_militares}",
        "",
    ]
    for item in report.items:
        lines.append(
            " | ".join(
                [
                    item.status,
                    item.filename,
                    item.nome or "-",
                    item.identidade_mascarada or "-",
                    f"eventos={item.eventos_count}",
                    f"pendencias={len(item.pending)}",
                ]
            )
        )
        if item.error:
            lines.append(f"  erro={item.error}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Importa PDFs de Folhas prontas para a Memoria do Compilador."
    )
    parser.add_argument("--input", required=True, help="Pasta contendo PDFs de Folhas.")
    parser.add_argument("--dry-run", action="store_true", help="Extrai sem gravar no banco.")
    parser.add_argument("--commit", action="store_true", help="Grava na Memoria do Compilador.")
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="Reprocessa PDFs ja importados por SHA e salva novo snapshot sem duplicar arquivo.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/outputs/compiler_memory_import",
        help="Diretorio para relatorios JSON/TXT.",
    )
    args = parser.parse_args()
    if args.dry_run == args.commit:
        parser.error("Use exatamente um modo: --dry-run ou --commit.")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        importer = CompilerReferenceImporter(
            db,
            dry_run=args.dry_run,
            refresh_existing=args.refresh_existing,
        )
        report = importer.import_folder(Path(args.input))

    suffix = "dry-run" if args.dry_run else "commit"
    json_path = output_dir / f"compiler_memory_import_{suffix}.json"
    txt_path = output_dir / f"compiler_memory_import_{suffix}.txt"
    json_path.write_text(json.dumps(report_to_dict(report), ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text(report_to_txt(report), encoding="utf-8")

    print(report_to_txt(report))
    print(f"JSON: {json_path}")
    print(f"TXT: {txt_path}")


if __name__ == "__main__":
    main()
