from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.web.dependencies.auth import require_permission
from apps.web.errors import bad_request
from modules.compilador.application.declaracao_template_catalog import (
    get_declaracoes_templates_root,
    get_declaracoes_templates_roots,
    list_declaracao_templates,
)
from scripts.prepare_declaracao_templates import (
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_PREPARATION_REPORT,
    default_declaracoes_source_root,
    prepare_templates_from_root,
    write_preparation_report,
)

router = APIRouter(prefix="/declaracoes", tags=["declaracoes"])


@router.get("")
def declaracoes_home(user=Depends(require_permission("compilador.generate_odt"))):
    root = get_declaracoes_templates_root()
    return {
        "module": "declaracoes",
        "status": "ready",
        "templates_root_configured": root is not None,
    }


@router.get("/modelos")
def list_modelos_declaracao(user=Depends(require_permission("compilador.generate_odt"))):
    root = get_declaracoes_templates_root()
    roots = get_declaracoes_templates_roots()
    items = list_declaracao_templates()
    categories = sorted({item.category for item in items})
    return {
        "root_configured": root is not None,
        "source_root": str(root) if root else None,
        "source_roots": [str(item) for item in roots],
        "total": len(items),
        "compilable": sum(1 for item in items if item.can_compile),
        "categories": categories,
        "items": [
            {
                "key": item.key,
                "filename": item.filename,
                "title": item.title,
                "category": item.category,
                "relative_path": item.relative_path,
                "extension": item.extension,
                "template_kind": item.template_kind,
                "can_compile": item.can_compile,
                "warnings": item.warnings,
            }
            for item in items
        ],
    }


@router.post("/modelos/preparar")
def prepare_modelos_declaracao(user=Depends(require_permission("compilador.generate_odt"))):
    source_root = default_declaracoes_source_root()
    if not source_root.exists() or not source_root.is_dir():
        raise bad_request(
            "ERR_DECLARACAO_TEMPLATE_SOURCE_NOT_FOUND",
            "Pasta de modelos de declaracao nao encontrada.",
        )

    results = prepare_templates_from_root(
        source_root=source_root,
        output_root=DEFAULT_OUTPUT_ROOT,
        overwrite=True,
    )
    write_preparation_report(DEFAULT_PREPARATION_REPORT, results)

    catalog_items = list_declaracao_templates()
    return {
        "status": "OK",
        "source_root_configured": True,
        "source_root": str(source_root),
        "output_root": str(DEFAULT_OUTPUT_ROOT),
        "report": str(DEFAULT_PREPARATION_REPORT),
        "total": len(results),
        "ready": sum(1 for item in results if item.status == "READY"),
        "ready_with_warnings": sum(1 for item in results if item.status == "READY_WITH_WARNINGS"),
        "skipped": sum(1 for item in results if item.status.startswith("SKIPPED")),
        "catalog_total": len(catalog_items),
        "catalog_compilable": sum(1 for item in catalog_items if item.can_compile),
    }
