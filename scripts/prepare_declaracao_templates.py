from __future__ import annotations

import argparse
import json
import re
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from infra.config import settings
from modules.compilador.application.declaracao_template_catalog import (
    DECLARACOES_MODELOS_ENV,
)
from modules.compilador.application.documento_compiler import (
    DECLARACAO_FLAG_NAMES,
    _replace_placeholder_in_tree,
)
from shared.utils.hashing import sha256_file


DEFAULT_OUTPUT_ROOT = settings.base_dir / "data" / "input" / "modelos" / "declaracoes"
DEFAULT_PREPARATION_REPORT = settings.base_dir / "data" / "output" / "declaracao_templates_preparados.json"
RECOMMENDED_DECLARACAO_FLAGS = {
    "NOME_COMPLETO",
    "POSTO_GRADUACAO",
    "IDENTIDADE",
    "CPF",
    "DATA_EXTENSO",
    "ASSINATURA_NOME",
    "ASSINATURA_FUNCAO",
}


@dataclass(frozen=True, slots=True)
class TemplatePreparationResult:
    source_path: str
    output_path: str
    status: str
    replacements: list[dict[str, str]]
    warnings: list[str]
    sha256: str | None = None


def prepare_declaracao_template(
    source_path: Path,
    output_path: Path,
    *,
    overwrite: bool = False,
) -> TemplatePreparationResult:
    if output_path.exists() and not overwrite:
        return TemplatePreparationResult(
            source_path=str(source_path),
            output_path=str(output_path),
            status="SKIPPED_EXISTS",
            replacements=[],
            warnings=["WARN_OUTPUT_EXISTS"],
            sha256=sha256_file(output_path),
        )

    text = _extract_odt_text(source_path)
    replacements = _build_replacements(text)
    warnings = _quality_warnings(replacements)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _copy_odt_with_replacements(source_path, output_path, replacements)
    return TemplatePreparationResult(
        source_path=str(source_path),
        output_path=str(output_path),
        status="READY_WITH_WARNINGS" if warnings else "READY",
        replacements=[{"source": source, "target": target, "code": code} for source, target, code in replacements],
        warnings=warnings,
        sha256=sha256_file(output_path),
    )


def prepare_templates_from_root(
    source_root: Path,
    output_root: Path,
    *,
    overwrite: bool = False,
    limit: int | None = None,
) -> list[TemplatePreparationResult]:
    results: list[TemplatePreparationResult] = []
    for source_path in _candidate_templates(source_root):
        relative = source_path.relative_to(source_root)
        output_path = output_root / relative.with_name(f"{relative.stem}_template_sisges.odt")
        results.append(prepare_declaracao_template(source_path, output_path, overwrite=overwrite))
        if limit and len(results) >= limit:
            break
    return results


def default_declaracoes_source_root() -> Path:
    return _default_source_root()


def write_preparation_report(path: Path, results: list[TemplatePreparationResult]) -> None:
    _write_report(path, results)


def _candidate_templates(root: Path) -> list[Path]:
    paths: list[Path] = []
    for path in root.rglob("*.odt"):
        if path.name.startswith(".~lock."):
            continue
        if "modelo" in " ".join([*path.relative_to(root).parts, path.stem]).lower():
            paths.append(path)
    return sorted(paths, key=lambda item: item.as_posix().lower())


def _extract_odt_text(path: Path) -> str:
    with zipfile.ZipFile(path, "r") as odt:
        content = odt.read("content.xml")
    return "".join(ET.fromstring(content).itertext())


def _build_replacements(text: str) -> list[tuple[str, str, str]]:
    replacements: list[tuple[str, str, str]] = []

    _add_regex_group(
        replacements,
        text,
        r"junto\s+(?:ao|a|à|aos|às)\s+(?P<value>.+?),\s+que\s+",
        "[INSTITUICAO_ENSINO]",
        "INSTITUICAO_ENSINO",
    )
    _add_regex_group(
        replacements,
        text,
        r"\bque\s+(?P<value>(?:o|a|O|A|Sr\.?|Sra\.?|Senhor|Senhora|Soldado|Soldada|Cabo|Sargento|Tenente|Capitão|Major|Coronel|[0-9][^\s]{0,3}\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇa-záéíóúâêôãõç ]+).*?),\s+brasileir[oa]",
        "[ARTIGO_MILITAR] [POSTO_GRADUACAO] [NOME_COMPLETO]",
        "MILITAR_IDENTIFICACAO",
    )
    _add_regex_group(
        replacements,
        text,
        r"CPF\s*(?:n\.?[º°]?|sob o nº|nº|n\.°)?\s*(?P<value>[0-9]{3}\.?[0-9]{3}\.?[0-9]{3}-?[0-9]{2})",
        "[CPF]",
        "CPF",
    )
    _add_regex_group(
        replacements,
        text,
        r"(?:Identidade Militar|Identidade)\s*(?:n\.?[º°]|nº)?\s*(?P<value>[0-9]{6,12}-?[0-9A-Za-z]?)",
        "[IDENTIDADE]",
        "IDENTIDADE",
    )
    _add_regex_group(
        replacements,
        text,
        r"\bRA\s*(?:n\.?[º°]|nº)?\s*(?P<value>[0-9]{6,14})",
        "[RA]",
        "RA",
    )
    _add_regex_group(
        replacements,
        text,
        r"(?:desde o dia|incorporad[oa] em|serviço militar no dia|licenciad[oa].{0,30}?(?:na data de|no dia)|será licenciad[oa].{0,30}?no dia)\s+(?P<value>[0-9]{1,2}(?:\s+de\s+[A-Za-zçÇ]+\s+de\s+[0-9]{4}|/[0-9]{1,2}/[0-9]{4}))",
        "[DATA_SERVICO]",
        "DATA_SERVICO",
    )
    _add_regex_group(
        replacements,
        text,
        r"Brasília-DF,\s*(?P<value>[0-9]{1,2}(?:º|°)?\s+de\s+[A-Za-zçÇ]+\s+de\s+[0-9]{4}|[0-9]{1,2}\s+de\s+[A-Za-zçÇ]+\s+de\s+[0-9]{4})",
        "[DATA_EXTENSO]",
        "DATA_EXTENSO",
    )
    _add_literal(replacements, text, "brasileiro", "brasileir[GENERO_BRASILEIRO]", "GENERO_BRASILEIRO")
    _add_literal(replacements, text, "brasileira", "brasileir[GENERO_BRASILEIRO]", "GENERO_BRASILEIRO")
    _add_literal(replacements, text, "impossibilitado", "[SITUACAO_AUSENCIA]", "SITUACAO_AUSENCIA")
    _add_literal(replacements, text, "impossibilitada", "[SITUACAO_AUSENCIA]", "SITUACAO_AUSENCIA")
    _add_literal(replacements, text, "do referido aluno", "[REFERENCIA_ALUNO]", "REFERENCIA_ALUNO")
    _add_literal(replacements, text, "da referida aluna", "[REFERENCIA_ALUNO]", "REFERENCIA_ALUNO")

    signature = _signature_candidates(text)
    if signature:
        name, function = signature
        _add_literal(replacements, text, name, "[ASSINATURA_NOME]", "ASSINATURA_NOME")
        _add_literal(replacements, text, function, "[ASSINATURA_FUNCAO]", "ASSINATURA_FUNCAO")

    return _dedupe_replacements(replacements)


def _signature_candidates(text: str) -> tuple[str, str] | None:
    match = re.search(
        r"(?P<name>[A-ZÁÉÍÓÚÂÊÔÃÕÇ ]{10,})\s*[–-]\s*(?P<role>(?:Coronel|Major|Cel|Maj|Tenente|Capitão).+)$",
        text,
    )
    if match:
        return match.group("name").strip(), match.group("role").strip()
    return None


def _add_regex_group(
    replacements: list[tuple[str, str, str]],
    text: str,
    pattern: str,
    target: str,
    code: str,
) -> None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match:
        _add_literal(replacements, text, match.group("value").strip(), target, code)


def _add_literal(
    replacements: list[tuple[str, str, str]],
    text: str,
    source: str,
    target: str,
    code: str,
) -> None:
    normalized = " ".join(source.split())
    if normalized and normalized in text and normalized != target:
        replacements.append((normalized, target, code))


def _dedupe_replacements(replacements: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    seen: set[str] = set()
    deduped: list[tuple[str, str, str]] = []
    for source, target, code in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
        key = f"{source}->{target}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append((source, target, code))
    return deduped


def _quality_warnings(replacements: list[tuple[str, str, str]]) -> list[str]:
    targets = " ".join(target for _, target, _ in replacements)
    found = {flag for flag in DECLARACAO_FLAG_NAMES if f"[{flag}]" in targets}
    missing = sorted(RECOMMENDED_DECLARACAO_FLAGS - found)
    return [f"WARN_DECLARACAO_TEMPLATE_FLAG_MISSING_{flag}" for flag in missing]


def _copy_odt_with_replacements(
    source_path: Path,
    output_path: Path,
    replacements: list[tuple[str, str, str]],
) -> None:
    with zipfile.ZipFile(source_path, "r") as source:
        entries = {info.filename: source.read(info.filename) for info in source.infolist()}

    for xml_name in ("content.xml", "styles.xml"):
        if xml_name not in entries:
            continue
        root = ET.fromstring(entries[xml_name])
        for literal, placeholder, _ in replacements:
            _replace_placeholder_in_tree(root, literal, placeholder)
        entries[xml_name] = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    with zipfile.ZipFile(output_path, "w") as output:
        if "mimetype" in entries:
            output.writestr("mimetype", entries["mimetype"], compress_type=zipfile.ZIP_STORED)
        for name, data in entries.items():
            if name == "mimetype":
                continue
            output.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)


def _default_source_root() -> Path:
    env = __import__("os").getenv(DECLARACOES_MODELOS_ENV)
    if env:
        return Path(env).expanduser().resolve()
    secretaria = Path.home() / "Downloads" / "secretaria"
    matches = [item for item in secretaria.iterdir() if item.is_dir() and item.name.startswith("006")]
    if matches:
        return matches[0].resolve()
    return secretaria / "006 - DECLARACOES"


def _write_report(path: Path, results: list[TemplatePreparationResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "total": len(results),
        "ready": sum(1 for item in results if item.status == "READY"),
        "ready_with_warnings": sum(1 for item in results if item.status == "READY_WITH_WARNINGS"),
        "skipped": sum(1 for item in results if item.status.startswith("SKIPPED")),
        "items": [asdict(item) for item in results],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepara copias ODT com flags SISGES para declaracoes.")
    parser.add_argument("--source-root", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_PREPARATION_REPORT)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_root = (args.source_root or _default_source_root()).resolve()
    output_root = args.output_root.resolve()
    candidates = _candidate_templates(source_root)
    if args.limit:
        candidates = candidates[: args.limit]

    if args.dry_run:
        print(json.dumps({"source_root": str(source_root), "output_root": str(output_root), "candidates": len(candidates)}, indent=2))
        return

    results: list[TemplatePreparationResult] = []
    for source_path in candidates:
        relative = source_path.relative_to(source_root)
        output_path = output_root / relative.with_name(f"{relative.stem}_template_sisges.odt")
        if source_path.resolve() == output_path.resolve():
            continue
        if source_path.exists():
            results.append(prepare_declaracao_template(source_path, output_path, overwrite=args.overwrite))

    _write_report(args.report, results)
    print(
        json.dumps(
            {
                "status": "OK",
                "source_root": str(source_root),
                "output_root": str(output_root),
                "total": len(results),
                "report": str(args.report),
            },
            ensure_ascii=False,
            indent=2,
        ),
    )


if __name__ == "__main__":
    main()
