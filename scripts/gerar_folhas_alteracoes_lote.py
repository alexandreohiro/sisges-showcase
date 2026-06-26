from __future__ import annotations

import argparse
from pathlib import Path

from infra.persistence.db import SessionLocal
from modules.compilador.application.folhas_batch_generator import (
    FolhasAlteracoesBatchGenerator,
    build_batch_txt_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fluxo operacional de geracao de Folhas de Alteracoes.")
    parser.add_argument("--ano", type=int, required=True)
    parser.add_argument("--semestre", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--output", default="data/output/folhas/2025_2sem")
    parser.add_argument("--modelo", default="")
    parser.add_argument("--sicapex-zip", default="data/input/SQL.zip")
    parser.add_argument("--militar-id", type=int)
    parser.add_argument("--identidade", default="")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--allow-pending-output", action="store_true", default=True)
    parser.add_argument("--empty-month-mode", default="BLOCK")
    args = parser.parse_args()
    if args.dry_run == args.commit:
        parser.error("Use exatamente um modo: --dry-run ou --commit.")

    db = SessionLocal()
    try:
        generator = FolhasAlteracoesBatchGenerator(
            db,
            output_dir=Path(args.output),
            ano=args.ano,
            semestre=args.semestre,
            modelo_odt=Path(args.modelo) if args.modelo else None,
            sicapex_zip=Path(args.sicapex_zip) if args.sicapex_zip else None,
            empty_month_mode=args.empty_month_mode,
        )
        result = generator.generate(
            dry_run=args.dry_run,
            militar_id=args.militar_id,
            identidade=args.identidade or None,
            limit=args.limit,
            allow_pending_output=args.allow_pending_output,
        )
        if args.commit:
            db.commit()
        print(build_batch_txt_report(result))
        print(f"Saida: {result.output_dir}")
        if result.package_path:
            print(f"Pacote geral: {result.package_path}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
