from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


DEFAULT_SECRETARIA_DATASET_DIR = Path("data/output/secretaria_dataset")
ASSISTED_REVIEW_RELATIVE_PATH = Path(
    "revisao_assistida_alteracoes/resumo_revisao_assistida_alteracoes.json",
)
SEMESTER_REVIEW_KEY_RE = re.compile(r"^20\d{2}_[12]sem$")
LOT_KEY_RE = re.compile(r"^[a-z0-9_]+$")
SECRETARIA_REPORTS = {
    "inventario_txt": Path("inventario_secretaria.txt"),
    "inventario_json": Path("inventario_secretaria.json"),
    "plano_txt": Path("plano_ingestao_secretaria_lancamento.txt"),
    "plano_json": Path("plano_ingestao_secretaria_lancamento.json"),
    "dry_run_alteracoes_txt": Path("dry_run_alteracoes/dry_run_alteracoes_001.txt"),
    "dry_run_alteracoes_json": Path("dry_run_alteracoes/dry_run_alteracoes_001.json"),
    "resumo_revisao_txt": Path(
        "revisao_assistida_alteracoes/resumo_revisao_assistida_alteracoes.txt",
    ),
    "resumo_revisao_json": Path(
        "revisao_assistida_alteracoes/resumo_revisao_assistida_alteracoes.json",
    ),
}


def load_secretaria_dataset_status(
    base_dir: Path | str = DEFAULT_SECRETARIA_DATASET_DIR,
) -> dict:
    root = Path(base_dir)
    inventory_path = root / "inventario_secretaria.json"
    plan_path = root / "plano_ingestao_secretaria_lancamento.json"
    assisted_review_path = root / ASSISTED_REVIEW_RELATIVE_PATH
    lots_dir = root / "lotes"

    if not inventory_path.exists():
        return {
            "available": False,
            "status": "INVENTARIO_AUSENTE",
            "message": "Inventario da pasta secretaria ainda nao foi gerado.",
            "inventory": None,
            "plan": None,
            "lots": [],
            "assisted_review": None,
            "reports": [],
            "operational_readiness": _build_missing_inventory_readiness(),
        }

    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else None
    assisted_review = (
        json.loads(assisted_review_path.read_text(encoding="utf-8"))
        if assisted_review_path.exists()
        else None
    )
    lot_items = []

    if lots_dir.exists():
        for path in sorted(lots_dir.glob("*.csv")):
            lot_items.append(
                {
                    "name": path.stem,
                    "filename": path.name,
                    "size_bytes": path.stat().st_size,
                }
            )

    reports = _list_secretaria_reports(root)
    compact_assisted_review = _compact_assisted_review(assisted_review)

    return {
        "available": True,
        "status": "INVENTARIO_DISPONIVEL",
        "message": "Inventario da pasta secretaria disponivel para triagem operacional.",
        "inventory": {
            "generated_at": inventory.get("generated_at"),
            "total_files": inventory.get("total_files", 0),
            "total_bytes": inventory.get("total_bytes", 0),
            "extension_counts": inventory.get("extension_counts", {}),
            "top_folder_counts": inventory.get("top_folder_counts", {}),
            "module_hint_counts": inventory.get("module_hint_counts", {}),
            "action_counts": inventory.get("action_counts", {}),
            "warnings": inventory.get("warnings", []),
        },
        "plan": _compact_plan(plan),
        "assisted_review": compact_assisted_review,
        "lots": lot_items,
        "reports": reports,
        "operational_readiness": _build_operational_readiness(
            plan=plan,
            assisted_review=compact_assisted_review,
            lots=lot_items,
            reports=reports,
        ),
    }


def _build_missing_inventory_readiness() -> dict:
    return {
        "status": "BLOQUEADO",
        "can_lan_dry_run": False,
        "blocking_count": 1,
        "warning_count": 0,
        "next_action": "Gerar inventario da pasta secretaria antes de qualquer ingestao.",
        "checks": [
            {
                "key": "inventory",
                "label": "Inventario",
                "status": "BLOCKED",
                "detail": "inventario_secretaria.json ausente.",
            },
        ],
    }


def _build_operational_readiness(
    *,
    plan: dict | None,
    assisted_review: dict | None,
    lots: list[dict],
    reports: list[dict],
) -> dict:
    checks = [
        {
            "key": "inventory",
            "label": "Inventario",
            "status": "OK",
            "detail": "Inventario disponivel para leitura operacional.",
        }
    ]

    go_no_go = plan.get("go_no_go", {}) if plan else {}
    lan_pilot = go_no_go.get("lan_pilot")
    bulk_import = go_no_go.get("bulk_import_to_db")
    checks.append(
        {
            "key": "plan",
            "label": "Plano de ingestao",
            "status": "OK" if plan else "BLOCKED",
            "detail": plan.get("recommended_release_step") if plan else "Plano de ingestao ausente.",
        }
    )
    checks.append(
        {
            "key": "lan_pilot",
            "label": "Piloto LAN",
            "status": "OK" if str(lan_pilot).startswith("GO") else "WARN",
            "detail": lan_pilot or "Sem decisao de piloto LAN no plano.",
        }
    )
    checks.append(
        {
            "key": "bulk_import",
            "label": "Importacao em massa",
            "status": "OK" if bulk_import and str(bulk_import).startswith("NO_GO") else "WARN",
            "detail": bulk_import or "Sem decisao para importacao em massa.",
        }
    )
    checks.append(
        {
            "key": "assisted_review",
            "label": "Revisao assistida",
            "status": "OK" if assisted_review else "WARN",
            "detail": f"{assisted_review.get('total_items', 0)} itens classificados."
            if assisted_review
            else "Resumo de revisao assistida ausente.",
        }
    )
    high_priority_count = (
        int(assisted_review.get("priority_counts", {}).get("HIGH", 0))
        if assisted_review
        else 0
    )
    checks.append(
        {
            "key": "high_priority_review",
            "label": "Pendencias altas",
            "status": "WARN" if high_priority_count else "OK",
            "detail": f"{high_priority_count} itens exigem revisao antes de importacao real.",
        }
    )
    checks.append(
        {
            "key": "lots",
            "label": "Lotes CSV",
            "status": "OK" if lots else "WARN",
            "detail": f"{len(lots)} lotes disponiveis para download.",
        }
    )
    checks.append(
        {
            "key": "reports",
            "label": "Relatorios",
            "status": "OK" if reports else "WARN",
            "detail": f"{len(reports)} relatorios operacionais disponiveis.",
        }
    )
    blocking_count = sum(1 for check in checks if check["status"] == "BLOCKED")
    warning_count = sum(1 for check in checks if check["status"] == "WARN")
    status = "BLOQUEADO" if blocking_count else "PRONTO_PARA_DRY_RUN_LAN"
    next_action = (
        "Resolver bloqueios antes de usar o dataset."
        if blocking_count
        else "Baixar pacote de auditoria e revisar pendencias altas antes de qualquer importacao real."
    )
    return {
        "status": status,
        "can_lan_dry_run": blocking_count == 0,
        "blocking_count": blocking_count,
        "warning_count": warning_count,
        "next_action": next_action,
        "checks": checks,
    }


def _compact_plan(plan: dict | None) -> dict | None:
    if not plan:
        return None
    return {
        "generated_at": plan.get("generated_at"),
        "recommended_release_step": plan.get("recommended_release_step"),
        "go_no_go": plan.get("go_no_go", {}),
        "phases": plan.get("phases", []),
    }


def _compact_assisted_review(review: dict | None) -> dict | None:
    if not review:
        return None
    return {
        "generated_at": review.get("generated_at"),
        "total_items": review.get("total_items", 0),
        "group_counts": review.get("group_counts", {}),
        "source_kind_counts": review.get("source_kind_counts", {}),
        "priority_counts": review.get("priority_counts", {}),
        "reason_counts": review.get("reason_counts", {}),
        "outputs": review.get("outputs", {}),
        "semester_outputs": _compact_semester_outputs(review),
    }


def _list_secretaria_reports(root: Path) -> list[dict]:
    items = []
    for key, relative_path in SECRETARIA_REPORTS.items():
        path = root / relative_path
        if not path.exists() or not path.is_file():
            continue
        items.append(
            {
                "key": key,
                "filename": path.name,
                "size_bytes": path.stat().st_size,
            }
        )
    return items


def _compact_semester_outputs(review: dict) -> list[dict]:
    outputs = review.get("outputs", {})
    raw_semester_dir = outputs.get("por_semestre")
    if not isinstance(raw_semester_dir, str) or not raw_semester_dir:
        return []

    semester_dir = Path(raw_semester_dir)
    if not semester_dir.is_absolute():
        semester_dir = Path.cwd() / semester_dir
    if not semester_dir.exists() or not semester_dir.is_dir():
        return []

    group_counts = review.get("group_counts", {})
    items = []
    for path in sorted(semester_dir.glob("*.csv")):
        key = path.stem
        if not SEMESTER_REVIEW_KEY_RE.match(key):
            continue
        items.append(
            {
                "key": key,
                "filename": path.name,
                "size_bytes": path.stat().st_size,
                "count": group_counts.get(key, 0),
            }
        )
    return sorted(items, key=lambda item: (-int(item["count"]), item["key"]))


def resolve_secretaria_review_output_path(
    output_key: str,
    base_dir: Path | str = DEFAULT_SECRETARIA_DATASET_DIR,
) -> Path | None:
    root = Path(base_dir).resolve()
    assisted_review_path = root / ASSISTED_REVIEW_RELATIVE_PATH
    if not assisted_review_path.exists():
        return None

    review = json.loads(assisted_review_path.read_text(encoding="utf-8"))
    outputs = review.get("outputs", {})
    raw_output_path = outputs.get(output_key)
    if not isinstance(raw_output_path, str) or not raw_output_path:
        return None

    output_path = Path(raw_output_path)
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path

    resolved_output_path = output_path.resolve()
    if root not in resolved_output_path.parents and resolved_output_path != root:
        return None
    if not resolved_output_path.exists() or not resolved_output_path.is_file():
        return None
    return resolved_output_path


def resolve_secretaria_semester_review_output_path(
    period_key: str,
    base_dir: Path | str = DEFAULT_SECRETARIA_DATASET_DIR,
) -> Path | None:
    if not SEMESTER_REVIEW_KEY_RE.match(period_key):
        return None

    root = Path(base_dir).resolve()
    assisted_review_path = root / ASSISTED_REVIEW_RELATIVE_PATH
    if not assisted_review_path.exists():
        return None

    review = json.loads(assisted_review_path.read_text(encoding="utf-8"))
    outputs = review.get("outputs", {})
    raw_semester_dir = outputs.get("por_semestre")
    if not isinstance(raw_semester_dir, str) or not raw_semester_dir:
        return None

    semester_dir = Path(raw_semester_dir)
    if not semester_dir.is_absolute():
        semester_dir = Path.cwd() / semester_dir
    resolved_semester_dir = semester_dir.resolve()
    if root not in resolved_semester_dir.parents and resolved_semester_dir != root:
        return None

    output_path = (resolved_semester_dir / f"{period_key}.csv").resolve()
    if resolved_semester_dir not in output_path.parents:
        return None
    if not output_path.exists() or not output_path.is_file():
        return None
    return output_path


def resolve_secretaria_lot_output_path(
    lot_name: str,
    base_dir: Path | str = DEFAULT_SECRETARIA_DATASET_DIR,
) -> Path | None:
    if not LOT_KEY_RE.match(lot_name):
        return None

    root = Path(base_dir).resolve()
    lots_dir = (root / "lotes").resolve()
    if root not in lots_dir.parents and lots_dir != root:
        return None

    output_path = (lots_dir / f"{lot_name}.csv").resolve()
    if lots_dir not in output_path.parents:
        return None
    if not output_path.exists() or not output_path.is_file():
        return None
    return output_path


def resolve_secretaria_report_output_path(
    report_key: str,
    base_dir: Path | str = DEFAULT_SECRETARIA_DATASET_DIR,
) -> Path | None:
    relative_path = SECRETARIA_REPORTS.get(report_key)
    if not relative_path:
        return None

    root = Path(base_dir).resolve()
    output_path = (root / relative_path).resolve()
    if root not in output_path.parents:
        return None
    if not output_path.exists() or not output_path.is_file():
        return None
    return output_path


def collect_secretaria_audit_artifacts(
    base_dir: Path | str = DEFAULT_SECRETARIA_DATASET_DIR,
) -> list[dict]:
    root = Path(base_dir).resolve()
    artifacts: list[dict] = []
    seen_paths: set[Path] = set()

    def add_artifact(path: Path, archive_path: str, role: str) -> None:
        resolved = path.resolve()
        if resolved in seen_paths:
            return
        if root not in resolved.parents and resolved != root:
            return
        if not resolved.exists() or not resolved.is_file():
            return
        seen_paths.add(resolved)
        artifacts.append(
            {
                "archive_path": archive_path.replace("\\", "/"),
                "path": resolved,
                "filename": resolved.name,
                "size_bytes": resolved.stat().st_size,
                "role": role,
            }
        )

    for key, relative_path in SECRETARIA_REPORTS.items():
        add_artifact(root / relative_path, f"RELATORIOS/{key}/{relative_path.name}", "REPORT")

    lots_dir = root / "lotes"
    if lots_dir.exists():
        for path in sorted(lots_dir.glob("*.csv")):
            if LOT_KEY_RE.match(path.stem):
                add_artifact(path, f"LOTES/{path.name}", "LOT")

    assisted_review_path = root / ASSISTED_REVIEW_RELATIVE_PATH
    if assisted_review_path.exists():
        review = json.loads(assisted_review_path.read_text(encoding="utf-8"))
        outputs = review.get("outputs", {})
        for key, raw_output_path in sorted(outputs.items()):
            if not isinstance(raw_output_path, str):
                continue
            output_path = Path(raw_output_path)
            if not output_path.is_absolute():
                output_path = Path.cwd() / output_path
            if output_path.is_file():
                add_artifact(output_path, f"REVISAO/{key}/{output_path.name}", "REVIEW")
            elif key == "por_semestre" and output_path.is_dir():
                for semester_path in sorted(output_path.glob("*.csv")):
                    if SEMESTER_REVIEW_KEY_RE.match(semester_path.stem):
                        add_artifact(
                            semester_path,
                            f"REVISAO/POR_SEMESTRE/{semester_path.name}",
                            "SEMESTER_REVIEW",
                        )

    return sorted(artifacts, key=lambda item: item["archive_path"])


def build_secretaria_audit_package(
    base_dir: Path | str = DEFAULT_SECRETARIA_DATASET_DIR,
) -> bytes | None:
    artifacts = collect_secretaria_audit_artifacts(base_dir)
    if not artifacts:
        return None

    manifest = {
        "schema_version": "sisges-secretaria-audit-package-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "total_files": len(artifacts),
        "files": [
            {
                "archive_path": item["archive_path"],
                "filename": item["filename"],
                "size_bytes": item["size_bytes"],
                "role": item["role"],
            }
            for item in artifacts
        ],
        "rules": [
            "Pacote gerado em memoria.",
            "Arquivos originais permanecem em data/output e fora do Git.",
            "Pacote contem apenas artefatos allowlistados da triagem secretaria.",
            "Este pacote nao importa dados no banco.",
        ],
    }

    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as zip_file:
        zip_file.writestr(
            "MANIFESTO_AUDITORIA_SECRETARIA.json",
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )
        for item in artifacts:
            zip_file.write(item["path"], item["archive_path"])
    return buffer.getvalue()
