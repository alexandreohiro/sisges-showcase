from __future__ import annotations

import argparse
from pathlib import Path

from infra.persistence.db import SessionLocal
from modules.compilador.application.folhas_batch_generator import (
    FolhasAlteracoesBatchGenerator,
    build_batch_txt_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reprocessa Folhas de Alteracoes existentes usando modelo ODT oficial."
    )
    parser.add_argument("--input", default="data/output/folhas")
    parser.add_argument("--modelo", required=True)
    parser.add_argument("--output", default="data/output/folhas_rebuild")
    parser.add_argument("--ano", type=int, default=2025)
    parser.add_argument("--semestre", default="2")
    parser.add_argument("--sicapex-zip", default="data/input/SQL.zip")
    parser.add_argument("--militar-id", type=int)
    parser.add_argument("--identidade", default="")
    parser.add_argument("--only-identidade", default="")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Entrada nao encontrada: {input_path}")
    modelo = Path(args.modelo)
    if not modelo.exists():
        raise SystemExit(f"Modelo ODT nao encontrado: {modelo}")

    db = SessionLocal()
    try:
        generator = FolhasAlteracoesBatchGenerator(
            db,
            output_dir=Path(args.output),
            ano=args.ano,
            semestre=args.semestre,
            modelo_odt=modelo,
            sicapex_zip=Path(args.sicapex_zip) if args.sicapex_zip else None,
        )
        result = generator.generate(
            dry_run=False,
            militar_id=args.militar_id,
            identidade=args.only_identidade or args.identidade or None,
            limit=args.limit,
            allow_pending_output=True,
        )
        db.commit()
        print(build_batch_txt_report(result))
        print(f"Entrada usada como referencia operacional: {input_path}")
        print(f"Saida reconstruida: {result.output_dir}")
        if result.package_path:
            print(f"Pacote geral: {result.package_path}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
