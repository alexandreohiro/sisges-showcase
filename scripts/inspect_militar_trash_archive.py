from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

import infra.persistence.models  # noqa: F401
from infra.persistence.db import SessionLocal
from modules.gestao_pessoal.application.deletion_archive import (
    dry_run_militar_deletion_archive_restore,
)


def inspect_archive(
    db: Session,
    archive_path: Path,
    *,
    expected_sha256: str | None = None,
    output_json: Path | None = None,
    output_txt: Path | None = None,
) -> dict[str, Any]:
    dry_run = dry_run_militar_deletion_archive_restore(
        db,
        archive_path,
        expected_sha256=expected_sha256,
    )
    report = {
        "schema_version": "sisges-militar-trash-inspection-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "archive_path": str(archive_path),
        "ok": dry_run.ok,
        "can_restore": dry_run.can_restore,
        "sha256": dry_run.validation.sha256,
        "errors": dry_run.errors,
        "warnings": dry_run.warnings,
        "conflicts": dry_run.conflicts,
        "validation": {
            "ok": dry_run.validation.ok,
            "summary": dry_run.validation.summary,
            "manifest": dry_run.validation.manifest,
        },
        "restore_plan": dry_run.restore_plan,
    }

    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_txt:
        output_txt.parent.mkdir(parents=True, exist_ok=True)
        output_txt.write_text(render_text_report(report), encoding="utf-8")

    return report


def render_text_report(report: dict[str, Any]) -> str:
    restore_plan = report.get("restore_plan") or {}
    militar = restore_plan.get("militar") or {}
    lines = [
        "RELATORIO DE INSPECAO DE LIXEIRA DE MILITAR",
        f"Gerado em: {report['generated_at']}",
        f"Arquivo: {report['archive_path']}",
        f"SHA-256: {report.get('sha256') or '-'}",
        f"ZIP valido: {'SIM' if report['ok'] else 'NAO'}",
        f"Restauracao tecnica possivel: {'SIM' if report['can_restore'] else 'NAO'}",
        "",
        "Militar:",
        f"- id: {militar.get('id') or '-'}",
        f"- identidade: {militar.get('identidade') or '-'}",
        f"- nome: {militar.get('nome_completo') or '-'}",
        "",
        "Plano:",
        f"- escreve no banco: {restore_plan.get('writes_database', False)}",
        f"- registros deletados: {restore_plan.get('total_deleted_records', 0)}",
        f"- vinculos a religar: {restore_plan.get('total_detached_records', 0)}",
        "",
        "Conflitos:",
    ]
    conflicts = report.get("conflicts") or []
    if conflicts:
        for conflict in conflicts:
            lines.append(f"- {conflict.get('code')}: {conflict.get('field')}={conflict.get('value')}")
    else:
        lines.append("- nenhum")

    lines.append("")
    lines.append("Erros:")
    errors = report.get("errors") or []
    if errors:
        lines.extend(f"- {error}" for error in errors)
    else:
        lines.append("- nenhum")

    lines.append("")
    lines.append("Avisos:")
    warnings = report.get("warnings") or []
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- nenhum")

    lines.append("")
    lines.append("Observacao: este comando nao restaura o banco. Ele apenas valida o ZIP e monta um plano tecnico.")
    return "\n".join(lines) + "\n"


def _run_with_session(
    db_factory: Callable[[], Session],
    *,
    archive_path: Path,
    expected_sha256: str | None,
    output_json: Path | None,
    output_txt: Path | None,
) -> dict[str, Any]:
    db = db_factory()
    try:
        report = inspect_archive(
            db,
            archive_path,
            expected_sha256=expected_sha256,
            output_json=output_json,
            output_txt=output_txt,
        )
        db.rollback()
        return report
    finally:
        db.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspeciona ZIP de lixeira de militar e monta dry-run de restauracao sem escrita.",
    )
    parser.add_argument("--archive", required=True, type=Path, help="Caminho do ZIP de lixeira.")
    parser.add_argument("--expected-sha256", default=None)
    parser.add_argument("--output-json", type=Path, default=Path("data/output/lixeira_militar_inspection.json"))
    parser.add_argument("--output-txt", type=Path, default=Path("data/output/lixeira_militar_inspection.txt"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = _run_with_session(
        SessionLocal,
        archive_path=args.archive,
        expected_sha256=args.expected_sha256,
        output_json=args.output_json,
        output_txt=args.output_txt,
    )
    print(render_text_report(report))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
