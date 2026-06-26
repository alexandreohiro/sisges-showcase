from __future__ import annotations

import argparse
import json
from pathlib import Path

from infra.persistence.db import SessionLocal
from modules.compilador.application.compiler_reference_importer import CompilerReferenceImporter
from scripts.import_compiler_references import report_to_dict, report_to_txt


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Importa PDFs de alteracoes/Folhas para a Memoria do Compilador."
    )
    parser.add_argument("--input", required=True, help="Pasta com PDFs de alteracoes.")
    parser.add_argument("--ano", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--refresh-existing", action="store_true")
    parser.add_argument(
        "--report",
        default="data/output/folhas/alteracoes_import.json",
        help="Caminho do relatorio JSON. Um TXT de mesmo nome tambem sera criado.",
    )
    args = parser.parse_args()
    if args.dry_run == args.commit:
        parser.error("Use exatamente um modo: --dry-run ou --commit.")

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        importer = CompilerReferenceImporter(
            db,
            dry_run=args.dry_run,
            refresh_existing=args.refresh_existing,
        )
        report = importer.import_folder(Path(args.input))

    payload = report_to_dict(report)
    payload["ano_requisitado"] = args.ano
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path = report_path.with_suffix(".txt")
    txt_path.write_text(report_to_txt(report), encoding="utf-8")

    unassociated = [
        item
        for item in payload["items"]
        if item.get("status") != "DUPLICATE_SHA"
        and (not item.get("militar_id") or item.get("pending") or item.get("status") == "FAILED")
    ]
    queue_path = report_path.parent / "eventos_sem_associacao.json"
    queue_path.write_text(json.dumps(unassociated, ensure_ascii=False, indent=2), encoding="utf-8")

    print(report_to_txt(report))
    print(f"JSON: {report_path}")
    print(f"TXT: {txt_path}")
    print(f"Fila sem associacao/pendencias: {queue_path}")


if __name__ == "__main__":
    main()
