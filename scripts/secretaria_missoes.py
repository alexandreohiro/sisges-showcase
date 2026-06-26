from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from infra.persistence.db import SessionLocal
from infra.persistence.models import CompilerFileModel, MilitarModel, SicapexImportFileModel


def main() -> None:
    parser = argparse.ArgumentParser(description="Controle operacional de missoes da secretaria.")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Cria matriz de trabalho para geracao de Folhas.")
    init.add_argument("--ano", type=int, required=True)
    init.add_argument("--semestre", required=True)
    init.add_argument("--output", default="data/output/folhas/missoes_2025.json")
    args = parser.parse_args()

    if args.command == "init":
        run_init(args.ano, str(args.semestre), Path(args.output))


def run_init(ano: int, semestre: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output.with_suffix(".csv")
    with SessionLocal() as db:
        militares = (
            db.query(MilitarModel)
            .filter(MilitarModel.ativo.is_(True))
            .order_by(MilitarModel.posto_graduacao.asc(), MilitarModel.nome_completo.asc())
            .all()
        )
        rows = []
        for militar in militares:
            tem_sicapex = (
                db.query(SicapexImportFileModel.id)
                .filter(SicapexImportFileModel.militar_id == militar.id)
                .first()
                is not None
            )
            tem_alteracoes = (
                db.query(CompilerFileModel.id)
                .filter(
                    CompilerFileModel.militar_id == militar.id,
                    CompilerFileModel.role == "MEMORY_REFERENCE_FOLHA_PDF",
                )
                .first()
                is not None
            )
            pendencias = []
            if not tem_sicapex:
                pendencias.append("SEM_SICAPEX")
            if not tem_alteracoes:
                pendencias.append("SEM_ALTERACOES")
            status = "PRONTO_PARA_GERAR"
            if not tem_sicapex:
                status = "SEM_SICAPEX"
            elif not tem_alteracoes:
                status = "SEM_ALTERACOES"
            rows.append(
                {
                    "prioridade": len(rows) + 1,
                    "militar_id": militar.id,
                    "nome_completo": militar.nome_completo,
                    "identidade": militar.identidade or "",
                    "posto_grad": militar.posto_graduacao or "",
                    "semestre": semestre,
                    "ano": ano,
                    "status": status,
                    "tem_sicapex": tem_sicapex,
                    "tem_alteracoes": tem_alteracoes,
                    "tempo_calculado": tem_sicapex,
                    "folha_gerada": False,
                    "validada": False,
                    "pendencias": pendencias,
                    "output_dir": "",
                    "arquivo_odt": "",
                    "arquivo_pdf": "",
                    "responsavel": "",
                    "observacoes": "",
                }
            )

    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "prioridade",
                "ano",
                "semestre",
                "militar_id",
                "posto_grad",
                "nome_completo",
                "identidade",
                "status",
                "pendencias",
                "arquivo_odt",
                "arquivo_pdf",
                "responsavel",
                "observacoes",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "prioridade": row["prioridade"],
                    "ano": row["ano"],
                    "semestre": row["semestre"],
                    "militar_id": row["militar_id"],
                    "posto_grad": row["posto_grad"],
                    "nome_completo": row["nome_completo"],
                    "identidade": row["identidade"],
                    "status": row["status"],
                    "pendencias": "; ".join(row["pendencias"]),
                    "arquivo_odt": row["arquivo_odt"],
                    "arquivo_pdf": row["arquivo_pdf"],
                    "responsavel": row["responsavel"],
                    "observacoes": row["observacoes"],
                }
            )
    print(f"JSON: {output}")
    print(f"CSV: {csv_path}")
    print(f"Itens: {len(rows)}")


if __name__ == "__main__":
    main()
