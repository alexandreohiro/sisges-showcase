from __future__ import annotations

import argparse
from pathlib import Path

from modules.gestao_pessoal.importadores.sicapex.batch_importer import SicapexBatchImporter
from modules.gestao_pessoal.importadores.sicapex.report import report_to_json, report_to_txt


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa ZIP de Fichas Cadastro SiCaPEx.")
    parser.add_argument("--input", required=True, help="Caminho do ZIP SiCaPEx.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--refresh-existing", action="store_true")
    parser.add_argument(
        "--report",
        default="data/output/folhas/sicapex_import.json",
        help="Caminho do relatorio JSON. Um TXT de mesmo nome tambem sera criado.",
    )
    args = parser.parse_args()
    if args.dry_run == args.commit:
        parser.error("Use exatamente um modo: --dry-run ou --commit.")

    input_path = Path(args.input)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    importer = SicapexBatchImporter(
        dry_run=args.dry_run,
        refresh_existing=args.refresh_existing,
    )
    report = importer.import_zip(input_path)
    txt_path = report_path.with_suffix(".txt")
    report_path.write_text(report_to_json(report), encoding="utf-8")
    txt_path.write_text(report_to_txt(report), encoding="utf-8")

    print(report_to_txt(report))
    print(f"JSON: {report_path}")
    print(f"TXT: {txt_path}")


if __name__ == "__main__":
    main()
