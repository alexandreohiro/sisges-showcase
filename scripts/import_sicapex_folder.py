from __future__ import annotations

import argparse
from pathlib import Path

from modules.gestao_pessoal.importadores.sicapex.batch_importer import SicapexBatchImporter
from modules.gestao_pessoal.importadores.sicapex.report import report_to_json, report_to_txt


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa PDFs de Ficha Cadastro SiCaPEx em lote.")
    parser.add_argument("--input", required=True, help="Pasta ou ZIP contendo PDFs SiCaPEx.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Extrai e valida sem gravar no banco.")
    mode.add_argument("--commit", action="store_true", help="Grava dados, auditoria e eventos no banco.")
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help=(
            "Reprocessa PDFs ja importados pelo mesmo SHA-256 e atualiza parsed_json, "
            "eventos e periodos sem criar duplicidade."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default="data/outputs/sicapex_import",
        help="Diretorio para relatorios JSON/TXT.",
    )
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    importer = SicapexBatchImporter(
        dry_run=args.dry_run,
        refresh_existing=args.refresh_existing,
    )
    if input_dir.is_file() and input_dir.suffix.lower() == ".zip":
        report = importer.import_zip(input_dir)
    else:
        report = importer.import_folder(input_dir)
    slug = report.batch_id if report.batch_id != "dry-run" else "dry-run"
    json_path = output_dir / f"sicapex_import_{slug}.json"
    txt_path = output_dir / f"sicapex_import_{slug}.txt"
    json_path.write_text(report_to_json(report), encoding="utf-8")
    txt_path.write_text(report_to_txt(report), encoding="utf-8")

    print(report_to_txt(report))
    print(f"JSON: {json_path}")
    print(f"TXT: {txt_path}")


if __name__ == "__main__":
    main()
