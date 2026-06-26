from __future__ import annotations

import hashlib
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path

from infra.config import settings
from modules.compilador.application.document_template_classifier import (
    EXECUTABLE_TEMPLATE,
    classify_document_template,
)
from modules.compilador.application.documento_compiler import DECLARACAO_FLAG_NAMES


DECLARACOES_MODELOS_ENV = "SISGES_DECLARACOES_MODELOS_DIR"


@dataclass(frozen=True, slots=True)
class DeclaracaoTemplateCatalogItem:
    key: str
    filename: str
    title: str
    category: str
    relative_path: str
    source_root: str
    extension: str
    template_kind: str
    can_compile: bool
    warnings: list[str]


def list_declaracao_templates() -> list[DeclaracaoTemplateCatalogItem]:
    roots = get_declaracoes_templates_roots()
    if not roots:
        return []

    items: list[DeclaracaoTemplateCatalogItem] = []
    seen_paths: set[Path] = set()
    for root in roots:
        for path in sorted(root.rglob("*.odt"), key=lambda item: item.as_posix().lower()):
            resolved_path = path.resolve()
            if resolved_path in seen_paths or _is_lock_file(path):
                continue
            seen_paths.add(resolved_path)
            relative = path.relative_to(root)
            if not _is_candidate_template(relative, path):
                continue
            items.append(_build_catalog_item(root, path))
    return sorted(items, key=lambda item: (not item.can_compile, item.category, item.title.lower()))


def resolve_declaracao_template_path(template_key: str) -> Path | None:
    normalized = (template_key or "").strip()
    if not normalized:
        return None

    for item in list_declaracao_templates():
        if item.key == normalized:
            root = Path(item.source_root)
            path = (root / item.relative_path).resolve()
            if _is_inside(path, root.resolve()) and path.exists():
                return path
    return None


def get_declaracoes_templates_root() -> Path | None:
    roots = get_declaracoes_templates_roots()
    return roots[0] if roots else None


def get_declaracoes_templates_roots() -> list[Path]:
    candidates: list[Path] = []
    configured = os.getenv(DECLARACOES_MODELOS_ENV)
    if configured:
        candidates.append(Path(configured))
        return _existing_unique_roots(candidates)
    candidates.append(settings.base_dir / "data" / "input" / "modelos" / "declaracoes")
    candidates.append(
        Path.home() / "Downloads" / "secretaria" / "006 - DECLARAÇOES",
    )

    return _existing_unique_roots(candidates)


def _existing_unique_roots(candidates: list[Path]) -> list[Path]:
    roots: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        if resolved.exists() and resolved.is_dir() and resolved not in seen:
            roots.append(resolved)
            seen.add(resolved)
    return roots


def _build_catalog_item(root: Path, path: Path) -> DeclaracaoTemplateCatalogItem:
    relative = path.relative_to(root)
    relative_text = relative.as_posix()
    flags = _has_declaracao_flags(path)
    classification = classify_document_template(path)
    executable = classification.classification == EXECUTABLE_TEMPLATE
    can_compile = flags or executable
    warnings: list[str] = []
    if not flags and not executable:
        warnings.append("WARN_DECLARACAO_TEMPLATE_NEEDS_FLAGS")

    return DeclaracaoTemplateCatalogItem(
        key=_template_key(root=root, relative_path=relative_text),
        filename=path.name,
        title=_title_from_path(path),
        category=_category_from_relative(relative),
        relative_path=relative_text,
        source_root=str(root),
        extension=path.suffix.lower(),
        template_kind="ODT_FLAGS" if flags else ("SISGES_EXECUTABLE" if executable else "VISUAL_REFERENCE"),
        can_compile=can_compile,
        warnings=warnings,
    )


def _template_key(*, root: Path, relative_path: str) -> str:
    payload = f"{root.resolve().as_posix()}::{relative_path}".lower()
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _is_lock_file(path: Path) -> bool:
    return path.name.startswith(".~lock.") or path.name.endswith("#")


def _is_candidate_template(relative: Path, path: Path) -> bool:
    combined = " ".join([*relative.parts, path.stem]).lower()
    return "modelo" in combined or _has_declaracao_flags(path)


def _has_declaracao_flags(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path, "r") as odt:
            text = "\n".join(
                odt.read(name).decode("utf-8", errors="ignore")
                for name in ("content.xml", "styles.xml")
                if name in odt.namelist()
            )
    except Exception:
        return False

    return any(f"[{flag}]" in text for flag in DECLARACAO_FLAG_NAMES) or "[NOME]" in text


def _category_from_relative(relative: Path) -> str:
    if len(relative.parts) <= 1:
        return "GERAL"
    first = relative.parts[0]
    return first.split(" - ", 1)[-1].strip().upper() or first.upper()


def _title_from_path(path: Path) -> str:
    title = path.stem.replace("_", " ").replace("-", " ")
    return " ".join(title.split())


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
