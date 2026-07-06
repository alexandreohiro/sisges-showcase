from __future__ import annotations

import argparse
import csv
import json
import re
from collections.abc import Iterable
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path


DEFAULT_INPUT = Path(
    "data/output/secretaria_dataset/lotes/importar_como_referencia_compilador_dry_run.csv",
)
DEFAULT_OUTPUT = Path("data/output/secretaria_dataset/dry_run_alteracoes")
DEFAULT_REVIEW_OUTPUT = Path("data/output/secretaria_dataset/revisao_assistida_alteracoes")

DATE_RANGE_RE = re.compile(
    r"(?P<start>\d{4}-\d{2}-\d{2})_(?P<end>\d{4}-\d{2}-\d{2})_(?P<label>.+)$",
    re.IGNORECASE,
)
SEMESTER_RE = re.compile(
    r"(?P<semester>[12])\s*[°º]?\s*SEM(?:ESTRE)?\s*(?P<year>20\d{2})",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"\b(?P<year>20\d{2})\b")
IDENTITY_PERIOD_RE = re.compile(
    r"^(?P<identity>\d{8,12}(?:-\d)?)[_\s-]+(?P<year>20\d{2})[_\s-]+(?P<semester>[12])(?:[._]\d+)?(?:[_\s-]+|$)",
    re.IGNORECASE,
)
LOOSE_SEMESTER_YEAR_RE = re.compile(
    r"(?P<semester>[12])\s*[°º]?\s+(?P<year>20\d{2})\b",
    re.IGNORECASE,
)

POSTO_GRAD_PATTERNS = [
    ("CEL", re.compile(r"\bCEL\b", re.IGNORECASE)),
    ("TC", re.compile(r"\b(TC|TEN\s*CEL|TENENTE\s*CORONEL)\b", re.IGNORECASE)),
    ("MAJ", re.compile(r"\bMAJ\b", re.IGNORECASE)),
    ("CAP", re.compile(r"\bCAP\b", re.IGNORECASE)),
    ("1 TEN", re.compile(r"\b1\s*[°º]?\s*TEN\b", re.IGNORECASE)),
    ("2 TEN", re.compile(r"\b2\s*[°º]?\s*TEN\b", re.IGNORECASE)),
    ("ASP", re.compile(r"\bASP\b", re.IGNORECASE)),
    ("ST", re.compile(r"\b(ST|S\s*TEN|SUBTEN|SUB\s*TEN)\b", re.IGNORECASE)),
    ("1 SGT", re.compile(r"\b1\s*[°º]?\s*SGT\b", re.IGNORECASE)),
    ("2 SGT", re.compile(r"\b2\s*[°º]?\s*SGT\b", re.IGNORECASE)),
    ("3 SGT", re.compile(r"\b3\s*[°º]?\s*SGT\b", re.IGNORECASE)),
    ("CB", re.compile(r"\bCB\b", re.IGNORECASE)),
    ("SD", re.compile(r"\bSD\b", re.IGNORECASE)),
]


@dataclass
class AlteracaoDryRunItem:
    relative_path: str
    filename: str
    extension: str
    size_bytes: int
    year: int | None = None
    semester: int | None = None
    posto_grad: str | None = None
    nome_hint: str | None = None
    date_start: str | None = None
    date_end: str | None = None
    status: str = "PENDING_REVIEW"
    warnings: list[str] = field(default_factory=list)


@dataclass
class AssistedReviewItem:
    relative_path: str
    filename: str
    source_kind: str
    year: int | None
    semester: int | None
    review_group: str
    posto_grad: str | None
    nome_hint: str | None
    status: str
    review_priority: str
    review_reason: str
    recommended_action: str
    warnings: list[str] = field(default_factory=list)


def _normalize_label(value: str) -> str:
    return _normalize_text(Path(value).stem)


def _normalize_text(value: str) -> str:
    cleaned = value
    cleaned = cleaned.replace("°", "°").replace("º", "º")
    cleaned = cleaned.replace("_", " ").replace("-", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _infer_semester_from_end_date(date_end: str) -> tuple[int | None, int | None]:
    year = int(date_end[:4])
    month = int(date_end[5:7])
    if 1 <= month <= 6:
        return year, 1
    if 7 <= month <= 12:
        return year, 2
    return year, None


def _extract_posto_grad(label: str) -> tuple[str | None, str]:
    for posto_grad, pattern in POSTO_GRAD_PATTERNS:
        match = pattern.search(label)
        if match:
            name = (label[: match.start()] + " " + label[match.end() :]).strip()
            return posto_grad, re.sub(r"\s+", " ", name).strip(" -_")
    return None, label


def _parent_label_hint(relative_path: str) -> str | None:
    generic_tokens = {
        _normalize_label(token).upper()
        for token in {
            "001 - ALTERAÇÕES",
            "001 - ALTERACOES",
            "000 - ALTERAÇÕES SCANEADAS",
            "000 - ALTERACOES SCANEADAS",
            "000 - LEGISLAÇÃO",
            "000 - LEGISLACAO",
        }
    }
    path = Path(relative_path)
    for part in reversed(path.parts[:-1]):
        cleaned = _normalize_label(part)
        upper = cleaned.upper()
        if not cleaned or upper in generic_tokens:
            continue
        if upper.startswith(("000 ", "001 ")) and "ALTERA" in upper:
            continue
        if cleaned.isdigit():
            continue
        if YEAR_RE.fullmatch(cleaned):
            continue
        return cleaned
    return None


def _should_use_parent_for_identity(label: str) -> bool:
    upper = label.upper()
    if re.fullmatch(r"\d{8,}", upper):
        return True
    if re.fullmatch(r"\d{8,}\s+\d{4,6}", upper):
        return True
    if upper.startswith("DOCUMENTO"):
        return True
    return not any(pattern.search(label) for _, pattern in POSTO_GRAD_PATTERNS)


def _path_period_hint(relative_path: str) -> tuple[int | None, int | None]:
    path = Path(relative_path)
    year = None
    semester = None
    parts = [_normalize_label(part) for part in path.parts[:-1]]

    for part in reversed(parts):
        if re.search(r"\b20\d{2}\s+a\s+20\d{2}\b", part, re.IGNORECASE):
            continue
        sem_match = SEMESTER_RE.search(part)
        if sem_match:
            return int(sem_match.group("year")), int(sem_match.group("semester"))
        loose_match = LOOSE_SEMESTER_YEAR_RE.search(part)
        if loose_match:
            return int(loose_match.group("year")), int(loose_match.group("semester"))
        semester_only_match = re.search(r"\b(?P<semester>[12])\s*[°º]?\s*SEM\b", part, re.IGNORECASE)
        if semester_only_match and not semester:
            semester = int(semester_only_match.group("semester"))
        if YEAR_RE.fullmatch(part):
            year = int(part)

    return year, semester


def classify_alteracao_row(row: dict[str, str]) -> AlteracaoDryRunItem:
    relative_path = row.get("relative_path", "")
    filename = Path(relative_path).name
    extension = (row.get("extension") or Path(filename).suffix).lower()
    size_bytes = int(row.get("size_bytes") or 0)
    warnings: list[str] = []

    label = _normalize_label(filename)
    date_start = None
    date_end = None
    year = None
    semester = None

    stem = Path(filename).stem
    date_match = DATE_RANGE_RE.match(stem)
    if date_match:
        date_start = date_match.group("start")
        date_end = date_match.group("end")
        label = _normalize_label(date_match.group("label"))
        year, semester = _infer_semester_from_end_date(date_end)
    else:
        identity_period_match = IDENTITY_PERIOD_RE.match(stem)
        if identity_period_match:
            year = int(identity_period_match.group("year"))
            semester = int(identity_period_match.group("semester"))
            parent_hint = _parent_label_hint(relative_path)
            label = _normalize_label(parent_hint) if parent_hint else label

        sem_match = SEMESTER_RE.search(label)
        if not identity_period_match and sem_match:
            year = int(sem_match.group("year"))
            semester = int(sem_match.group("semester"))
            label = SEMESTER_RE.sub("", label).strip()
        elif not identity_period_match:
            loose_semester_match = LOOSE_SEMESTER_YEAR_RE.search(label)
            if loose_semester_match:
                year = int(loose_semester_match.group("year"))
                semester = int(loose_semester_match.group("semester"))
                label = LOOSE_SEMESTER_YEAR_RE.sub("", label).strip()
            else:
                year_match = YEAR_RE.search(label)
                if year_match:
                    year = int(year_match.group("year"))
                    label = YEAR_RE.sub("", label).strip()

    path_year, path_semester = _path_period_hint(relative_path)
    if not year and path_year:
        year = path_year
    if not semester and path_semester:
        semester = path_semester
    parent_hint = _parent_label_hint(relative_path)
    if parent_hint and _should_use_parent_for_identity(label):
        label = parent_hint

    posto_grad, nome_hint = _extract_posto_grad(label)
    nome_hint = re.sub(r"\s+", " ", nome_hint).strip(" -_") or None

    if extension != ".pdf":
        warnings.append("WARN_NOT_PDF")
    if not year:
        warnings.append("WARN_YEAR_NOT_INFERRED")
    if not semester:
        warnings.append("WARN_SEMESTER_NOT_INFERRED")
    if not posto_grad:
        warnings.append("WARN_POSTO_GRAD_NOT_INFERRED")
    if not nome_hint or nome_hint.lower() in {"lista", "alteracoes", "alterações"}:
        warnings.append("WARN_MILITAR_NAME_NOT_INFERRED")
        nome_hint = None

    status = "READY_FOR_REFERENCE_DRY_RUN" if not warnings else "REVIEW_FILENAME_BEFORE_IMPORT"

    return AlteracaoDryRunItem(
        relative_path=relative_path,
        filename=filename,
        extension=extension,
        size_bytes=size_bytes,
        year=year,
        semester=semester,
        posto_grad=posto_grad,
        nome_hint=nome_hint.upper() if nome_hint else None,
        date_start=date_start,
        date_end=date_end,
        status=status,
        warnings=warnings,
    )


def run_dry_run(input_csv: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(input_csv.read_text(encoding="utf-8").splitlines()))
    items = [classify_alteracao_row(row) for row in rows]

    status_counts = Counter(item.status for item in items)
    warning_counts = Counter(warning for item in items for warning in item.warnings)
    year_counts = Counter(str(item.year) for item in items if item.year)
    semester_counts = Counter(
        f"{item.year}_{item.semester}sem"
        for item in items
        if item.year and item.semester
    )
    posto_counts = Counter(item.posto_grad for item in items if item.posto_grad)

    payload = {
        "schema_version": "secretaria-alteracoes-dry-run-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "input_csv": str(input_csv),
        "total_items": len(items),
        "status_counts": dict(status_counts),
        "warning_counts": dict(warning_counts),
        "year_counts": dict(year_counts),
        "semester_counts": dict(semester_counts),
        "posto_grad_counts": dict(posto_counts),
        "items": [asdict(item) for item in items],
    }

    json_path = output_dir / "dry_run_alteracoes_001.json"
    txt_path = output_dir / "dry_run_alteracoes_001.txt"
    csv_path = output_dir / "dry_run_alteracoes_001.csv"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_txt_report(payload, txt_path)
    _write_csv(items, csv_path)

    return {
        "json": str(json_path),
        "txt": str(txt_path),
        "csv": str(csv_path),
        "total_items": len(items),
        "status_counts": dict(status_counts),
        "warning_counts": dict(warning_counts),
    }


def run_assisted_review(dry_run_json: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = json.loads(dry_run_json.read_text(encoding="utf-8"))
    items = [_review_item(item) for item in payload.get("items", [])]

    group_counts = Counter(item.review_group for item in items)
    source_kind_counts = Counter(item.source_kind for item in items)
    priority_counts = Counter(item.review_priority for item in items)
    reason_counts = Counter(item.review_reason for item in items)

    summary = {
        "schema_version": "secretaria-alteracoes-assisted-review-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_dry_run": str(dry_run_json),
        "total_items": len(items),
        "group_counts": dict(group_counts),
        "source_kind_counts": dict(source_kind_counts),
        "priority_counts": dict(priority_counts),
        "reason_counts": dict(reason_counts),
        "outputs": {},
    }

    all_csv = output_dir / "revisao_assistida_alteracoes.csv"
    _write_review_csv(items, all_csv)
    summary["outputs"]["all"] = str(all_csv)

    outputs_by_filter = {
        "revisar_nome_nao_identificado.csv": lambda item: "WARN_MILITAR_NAME_NOT_INFERRED"
        in item.warnings,
        "revisar_periodo_nao_identificado.csv": lambda item: (
            "WARN_YEAR_NOT_INFERRED" in item.warnings
            or "WARN_SEMESTER_NOT_INFERRED" in item.warnings
        ),
        "revisar_posto_grad_nao_identificado.csv": lambda item: "WARN_POSTO_GRAD_NOT_INFERRED"
        in item.warnings,
        "prontos_para_referencia_por_nome.csv": lambda item: item.review_priority == "LOW",
        "revisar_documento_normativo_ou_generico.csv": lambda item: item.source_kind
        in {"DOCUMENTO_NORMATIVO", "LISTA_GENERICA"},
        "revisar_escaneamento_sem_periodo.csv": lambda item: item.source_kind
        in {"ESCANEAMENTO_TIMESTAMP", "HISTORICO_ESCANEADO", "ESCANEAMENTO_AVULSO"}
        and item.review_group == "SEM_PERIODO",
    }
    for filename, predicate in outputs_by_filter.items():
        selected = [item for item in items if predicate(item)]
        path = output_dir / filename
        _write_review_csv(selected, path)
        summary["outputs"][Path(filename).stem] = str(path)

    grouped_dir = output_dir / "por_semestre"
    grouped_dir.mkdir(parents=True, exist_ok=True)
    for group in sorted(group_counts):
        selected = [item for item in items if item.review_group == group]
        path = grouped_dir / f"{_safe_filename(group)}.csv"
        _write_review_csv(selected, path)

    summary["outputs"]["por_semestre"] = str(grouped_dir)

    json_path = output_dir / "resumo_revisao_assistida_alteracoes.json"
    txt_path = output_dir / "resumo_revisao_assistida_alteracoes.txt"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_review_txt(summary, txt_path)
    summary["outputs"]["summary_json"] = str(json_path)
    summary["outputs"]["summary_txt"] = str(txt_path)
    return summary


def _write_txt_report(payload: dict, path: Path) -> None:
    lines = [
        "DRY-RUN 001 - ALTERACOES / SISGES",
        f"Gerado em: {payload['generated_at']}",
        f"Fonte: {payload['input_csv']}",
        f"Total: {payload['total_items']}",
        "",
        "Status:",
        *[f"- {key}: {value}" for key, value in payload["status_counts"].items()],
        "",
        "Warnings:",
        *[f"- {key}: {value}" for key, value in payload["warning_counts"].items()],
        "",
        "Semestres inferidos:",
        *[
            f"- {key}: {value}"
            for key, value in sorted(payload["semester_counts"].items())
        ],
        "",
        "Postos/graduações inferidos:",
        *[
            f"- {key}: {value}"
            for key, value in sorted(payload["posto_grad_counts"].items())
        ],
        "",
        "Regra operacional:",
        "- Este dry-run nao abre PDFs.",
        "- Este dry-run nao grava banco.",
        "- Este dry-run nao copia arquivos para o repositorio.",
        "- Entradas com warning devem ser revisadas antes de importacao controlada.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_csv(items: list[AlteracaoDryRunItem], path: Path) -> None:
    fieldnames = list(asdict(items[0]).keys()) if items else list(AlteracaoDryRunItem.__dataclass_fields__)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in items:
            row = asdict(item)
            row["warnings"] = "|".join(item.warnings)
            writer.writerow(row)


def _review_item(raw: dict) -> AssistedReviewItem:
    warnings = list(raw.get("warnings") or [])
    source_kind = _classify_source_kind(raw)
    year = raw.get("year")
    semester = raw.get("semester")
    review_group = f"{year}_{semester}sem" if year and semester else "SEM_PERIODO"

    if source_kind == "DOCUMENTO_NORMATIVO":
        priority = "MEDIUM"
        reason = "DOCUMENTO_NORMATIVO_EM_ALTERACOES"
        action = "Triar para Documentos/Ajuda normativa, nao importar diretamente no Compilador."
    elif source_kind == "LISTA_GENERICA":
        priority = "HIGH"
        reason = "LISTA_GENERICA_SEM_MILITAR"
        action = "Abrir manualmente e decidir se e indice, relacao ou fonte de associacao."
    elif "WARN_MILITAR_NAME_NOT_INFERRED" in warnings:
        priority = "HIGH"
        reason = "NOME_NAO_IDENTIFICADO"
        action = "Conferir arquivo e preencher militar antes de importar."
    elif "WARN_YEAR_NOT_INFERRED" in warnings or "WARN_SEMESTER_NOT_INFERRED" in warnings:
        priority = "HIGH"
        reason = "PERIODO_NAO_IDENTIFICADO"
        action = "Definir ano e semestre antes de associar ao Compilador."
    elif "WARN_POSTO_GRAD_NOT_INFERRED" in warnings:
        priority = "MEDIUM"
        reason = "POSTO_GRAD_NAO_IDENTIFICADO"
        action = "Conferir posto/graduação para melhorar associação."
    elif warnings:
        priority = "MEDIUM"
        reason = "OUTRA_PENDENCIA"
        action = "Revisar warnings antes da importação controlada."
    else:
        priority = "LOW"
        reason = "METADADOS_MINIMOS_INFERIDOS"
        action = "Pode seguir para dry-run de referência do Compilador."

    return AssistedReviewItem(
        relative_path=str(raw.get("relative_path") or ""),
        filename=str(raw.get("filename") or ""),
        source_kind=source_kind,
        year=year,
        semester=semester,
        review_group=review_group,
        posto_grad=raw.get("posto_grad"),
        nome_hint=raw.get("nome_hint"),
        status=str(raw.get("status") or "PENDING_REVIEW"),
        review_priority=priority,
        review_reason=reason,
        recommended_action=action,
        warnings=warnings,
    )


def _classify_source_kind(raw: dict) -> str:
    relative_path = str(raw.get("relative_path") or "")
    filename = str(raw.get("filename") or "")
    normalized_path = _normalize_text(relative_path).upper()
    normalized_filename = _normalize_label(filename).upper()

    if "LEGIS" in normalized_path:
        return "DOCUMENTO_NORMATIVO"
    if normalized_filename in {"LISTA", "INDICE", "ÍNDICE"}:
        return "LISTA_GENERICA"
    if re.fullmatch(r"20\d{12,}", Path(filename).stem):
        return "ESCANEAMENTO_TIMESTAMP"
    if re.search(r"\b20\d{2}\s+A\s+20\d{2}\b", normalized_path):
        return "HISTORICO_ESCANEADO"
    if any(token in normalized_path for token in {"SCANEADAS", "ESCANEADAS", "SCANER"}):
        return "ESCANEAMENTO_AVULSO"
    return "FOLHA_ALTERACAO_CANDIDATA"


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "sem_nome"


def _write_review_csv(items: Iterable[AssistedReviewItem], path: Path) -> None:
    fieldnames = list(AssistedReviewItem.__dataclass_fields__)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in items:
            row = asdict(item)
            row["warnings"] = "|".join(item.warnings)
            writer.writerow(row)


def _write_review_txt(summary: dict, path: Path) -> None:
    lines = [
        "REVISAO ASSISTIDA 001 - ALTERACOES / SISGES",
        f"Gerado em: {summary['generated_at']}",
        f"Fonte: {summary['source_dry_run']}",
        f"Total: {summary['total_items']}",
        "",
        "Prioridades:",
        *[f"- {key}: {value}" for key, value in summary["priority_counts"].items()],
        "",
        "Tipos de origem:",
        *[f"- {key}: {value}" for key, value in summary["source_kind_counts"].items()],
        "",
        "Motivos:",
        *[f"- {key}: {value}" for key, value in summary["reason_counts"].items()],
        "",
        "Grupos por semestre:",
        *[f"- {key}: {value}" for key, value in sorted(summary["group_counts"].items())],
        "",
        "Regra operacional:",
        "- Esta revisao nao abre PDFs.",
        "- Esta revisao nao grava banco.",
        "- Esta revisao separa filas de trabalho para conferencia humana.",
        "- Casos HIGH devem ser corrigidos antes de importacao controlada.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dry-run de alteracoes da pasta secretaria.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--assist-review",
        action="store_true",
        help="gera filas de revisao assistida apos o dry-run",
    )
    parser.add_argument(
        "--review-output",
        default=str(DEFAULT_REVIEW_OUTPUT),
        help="diretorio da revisao assistida",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run_dry_run(Path(args.input), Path(args.output))
    if args.assist_review:
        result["assisted_review"] = run_assisted_review(
            Path(result["json"]),
            Path(args.review_output),
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
