from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from shared.utils.hashing import sha256_file


DEFAULT_INPUT = Path(os.getenv("SISGES_SECRETARIA_INPUT_DIR", "data/input/secretaria"))
DEFAULT_OUTPUT = Path("data/output/secretaria_dataset")

SUPPORTED_DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".odt",
    ".docx",
    ".doc",
    ".ods",
    ".xlsx",
    ".xls",
    ".pptx",
    ".ppt",
    ".odp",
    ".odg",
    ".txt",
    ".md",
    ".json",
}

IGNORED_EXTENSIONS = {
    ".tmp",
    ".crdownload",
    ".url",
    ".php",
    ".js",
    ".css",
    ".dockerfile",
    ".sh",
    ".gz",
    ".ini",
    ".yaml",
    ".vcf",
    ".jfif",
    ".jpeg",
}

TOP_FOLDER_MODULE_HINTS = {
    "001": "folhas_alteracoes_compilador",
    "014": "legislacao_documentos",
    "015": "protocolo_documentos_tarefas",
    "017": "material_carga_documentos",
    "018": "honra_ao_merito_documentos",
    "020": "pop_ajuda_operacional",
    "021": "tcms_calculo_tempo_ctsm",
    "022": "carta_recomendacao_declaracoes",
}


@dataclass
class SecretariaFileItem:
    relative_path: str
    top_folder: str
    extension: str
    size_bytes: int
    last_modified: str
    module_hint: str
    action: str
    sha256: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class SecretariaInventory:
    schema_version: str
    generated_at: str
    source_root: str
    total_files: int
    total_bytes: int
    extension_counts: dict[str, int]
    top_folder_counts: dict[str, int]
    module_hint_counts: dict[str, int]
    action_counts: dict[str, int]
    samples: list[SecretariaFileItem]
    warnings: list[str]


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def normalize_extension(path: Path) -> str:
    return path.suffix.lower() or "[sem_extensao]"


def top_folder_for(path: Path, root: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return "[fora_da_raiz]"
    return relative.parts[0] if relative.parts else "[raiz]"


def module_hint_for(top_folder: str) -> str:
    prefix = top_folder.split(" ", 1)[0].strip()
    return TOP_FOLDER_MODULE_HINTS.get(prefix, "documentos_gerais_revisar")


def action_for(extension: str, module_hint: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if extension in IGNORED_EXTENSIONS:
        return "IGNORAR_ARTEFATO_TECNICO_OU_TEMPORARIO", warnings
    if extension not in SUPPORTED_DOCUMENT_EXTENSIONS:
        warnings.append("WARN_EXTENSAO_NAO_MAPEADA")
        return "REVISAR_MANUALMENTE", warnings
    if module_hint == "folhas_alteracoes_compilador" and extension == ".pdf":
        return "IMPORTAR_COMO_REFERENCIA_COMPILADOR_DRY_RUN", warnings
    if module_hint == "folhas_alteracoes_compilador" and extension == ".odt":
        return "CLASSIFICAR_ODT_FONTE_OU_MODELO_DRY_RUN", warnings
    if module_hint == "legislacao_documentos":
        return "INDEXAR_DOCUMENTO_NORMATIVO_DRY_RUN", warnings
    if module_hint == "pop_ajuda_operacional":
        return "INDEXAR_AJUDA_OPERACIONAL_DRY_RUN", warnings
    if module_hint == "tcms_calculo_tempo_ctsm":
        return "INDEXAR_TCMS_CTSM_DRY_RUN", warnings
    if module_hint == "carta_recomendacao_declaracoes":
        return "INDEXAR_MODELO_DECLARACAO_DRY_RUN", warnings
    return "INDEXAR_DOCUMENTO_GERAL_DRY_RUN", warnings


def iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file():
            yield path


def build_file_item(path: Path, root: Path, *, include_hash: bool = False) -> SecretariaFileItem:
    extension = normalize_extension(path)
    top_folder = top_folder_for(path, root)
    module_hint = module_hint_for(top_folder)
    action, warnings = action_for(extension, module_hint)
    stat = path.stat()
    return SecretariaFileItem(
        relative_path=str(path.relative_to(root)).replace("\\", "/"),
        top_folder=top_folder,
        extension=extension,
        size_bytes=stat.st_size,
        last_modified=datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
        module_hint=module_hint,
        action=action,
        sha256=sha256_file(path) if include_hash else None,
        warnings=warnings,
    )


def build_inventory(
    source_root: Path,
    *,
    include_hash: bool = False,
    sample_limit: int = 300,
) -> SecretariaInventory:
    if not source_root.exists():
        raise FileNotFoundError(f"Pasta nao encontrada: {source_root}")
    if not source_root.is_dir():
        raise NotADirectoryError(f"Caminho nao e pasta: {source_root}")

    extension_counts: Counter[str] = Counter()
    top_folder_counts: Counter[str] = Counter()
    module_hint_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    samples: list[SecretariaFileItem] = []
    total_files = 0
    total_bytes = 0
    warnings: list[str] = []

    for path in iter_files(source_root):
        extension = normalize_extension(path)
        top_folder = top_folder_for(path, source_root)
        module_hint = module_hint_for(top_folder)
        action, item_warnings = action_for(extension, module_hint)
        size = path.stat().st_size

        total_files += 1
        total_bytes += size
        extension_counts[extension] += 1
        top_folder_counts[top_folder] += 1
        module_hint_counts[module_hint] += 1
        action_counts[action] += 1
        warnings.extend(item_warnings)

        if len(samples) < sample_limit:
            samples.append(build_file_item(path, source_root, include_hash=include_hash))

    return SecretariaInventory(
        schema_version="sisges-secretaria-dataset-inventory-v1",
        generated_at=now_iso(),
        source_root=str(source_root),
        total_files=total_files,
        total_bytes=total_bytes,
        extension_counts=dict(sorted(extension_counts.items())),
        top_folder_counts=dict(sorted(top_folder_counts.items())),
        module_hint_counts=dict(sorted(module_hint_counts.items())),
        action_counts=dict(sorted(action_counts.items())),
        samples=samples,
        warnings=sorted(set(warnings)),
    )


def inventory_to_dict(inventory: SecretariaInventory) -> dict:
    payload = asdict(inventory)
    payload["samples"] = [asdict(item) for item in inventory.samples]
    return payload


def inventory_to_txt(inventory: SecretariaInventory) -> str:
    lines = [
        "INVENTARIO DATASET SECRETARIA - SISGES",
        f"Gerado em: {inventory.generated_at}",
        f"Fonte: {inventory.source_root}",
        f"Total de arquivos: {inventory.total_files}",
        f"Total de bytes: {inventory.total_bytes}",
        "",
        "Modulos sugeridos:",
    ]
    for name, count in sorted(inventory.module_hint_counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {name}: {count}")

    lines.extend(["", "Acoes sugeridas:"])
    for name, count in sorted(inventory.action_counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {name}: {count}")

    lines.extend(["", "Extensoes:"])
    for name, count in sorted(inventory.extension_counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {name}: {count}")

    lines.extend(["", "Pastas principais:"])
    for name, count in sorted(inventory.top_folder_counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {name}: {count}")

    if inventory.warnings:
        lines.extend(["", "Warnings:"])
        for warning in inventory.warnings:
            lines.append(f"- {warning}")

    lines.extend(
        [
            "",
            "Regra operacional:",
            "- Este inventario nao copia arquivos para o repositorio.",
            "- Este inventario nao grava no banco.",
            "- Importacao em commit deve ser feita por modulo, com dry-run aprovado.",
            "- Arquivos sensiveis permanecem fora do Git.",
        ]
    )
    return "\n".join(lines)


def build_launch_plan(inventory: SecretariaInventory) -> dict:
    return {
        "schema_version": "sisges-secretaria-launch-plan-v1",
        "generated_at": now_iso(),
        "source_root": inventory.source_root,
        "recommended_release_step": "PILOTO_LAN_COM_STAGING_SECRETARIA",
        "go_no_go": {
            "lan_pilot": "GO_COM_DRY_RUN",
            "bulk_import_to_db": "NO_GO_ATE_APROVACAO_DO_INVENTARIO",
            "public_production": "NO_GO",
        },
        "phases": [
            {
                "phase": "1_INVENTARIO",
                "status": "DONE",
                "criteria": "quantitativo, extensoes e pastas principais conhecidos",
            },
            {
                "phase": "2_TRIAGEM_POR_MODULO",
                "status": "NEXT",
                "criteria": "separar alteracoes, legislacao, protocolo, POP, TCMS e declaracoes",
            },
            {
                "phase": "3_IMPORTACAO_DRY_RUN",
                "status": "NEXT",
                "criteria": "executar dry-run por modulo sem gravar banco",
            },
            {
                "phase": "4_IMPORTACAO_COMMIT_CONTROLADA",
                "status": "BLOCKED_UNTIL_APPROVAL",
                "criteria": "somente apos relatorio dry-run aprovado",
            },
            {
                "phase": "5_VALIDACAO_UI",
                "status": "NEXT",
                "criteria": "dados importados visiveis nos modulos corretos",
            },
        ],
        "module_hint_counts": inventory.module_hint_counts,
        "action_counts": inventory.action_counts,
        "warnings": inventory.warnings,
    }


def write_outputs(inventory: SecretariaInventory, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    inventory_json = output_dir / "inventario_secretaria.json"
    inventory_txt = output_dir / "inventario_secretaria.txt"
    plan_json = output_dir / "plano_ingestao_secretaria_lancamento.json"
    plan_txt = output_dir / "plano_ingestao_secretaria_lancamento.txt"

    inventory_json.write_text(
        json.dumps(inventory_to_dict(inventory), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    inventory_txt.write_text(inventory_to_txt(inventory), encoding="utf-8")

    plan = build_launch_plan(inventory)
    plan_json.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    plan_txt.write_text(plan_to_txt(plan), encoding="utf-8")
    return {
        "inventory_json": inventory_json,
        "inventory_txt": inventory_txt,
        "plan_json": plan_json,
        "plan_txt": plan_txt,
    }


def safe_batch_name(value: str) -> str:
    return (
        value.lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace("-", "_")
        .replace("[", "")
        .replace("]", "")
    )


def write_batch_lists(source_root: Path, output_dir: Path) -> dict[str, Path]:
    batches_dir = output_dir / "lotes"
    batches_dir.mkdir(parents=True, exist_ok=True)
    handles: dict[str, tuple[Path, object, csv.DictWriter]] = {}

    try:
        for path in iter_files(source_root):
            item = build_file_item(path, source_root, include_hash=False)
            key = safe_batch_name(item.action)
            if key not in handles:
                csv_path = batches_dir / f"{key}.csv"
                file_handle = csv_path.open("w", encoding="utf-8", newline="")
                writer = csv.DictWriter(
                    file_handle,
                    fieldnames=[
                        "relative_path",
                        "top_folder",
                        "extension",
                        "size_bytes",
                        "module_hint",
                        "action",
                        "warnings",
                    ],
                )
                writer.writeheader()
                handles[key] = (csv_path, file_handle, writer)
            _, _, writer = handles[key]
            writer.writerow(
                {
                    "relative_path": item.relative_path,
                    "top_folder": item.top_folder,
                    "extension": item.extension,
                    "size_bytes": item.size_bytes,
                    "module_hint": item.module_hint,
                    "action": item.action,
                    "warnings": ";".join(item.warnings),
                }
            )
    finally:
        for _, file_handle, _ in handles.values():
            file_handle.close()

    return {key: value[0] for key, value in sorted(handles.items())}


def plan_to_txt(plan: dict) -> str:
    lines = [
        "PLANO DE INGESTAO DA PASTA SECRETARIA - SISGES",
        f"Gerado em: {plan['generated_at']}",
        f"Fonte: {plan['source_root']}",
        "",
        "Decisao:",
    ]
    for key, value in plan["go_no_go"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "Fases:"])
    for phase in plan["phases"]:
        lines.append(f"- {phase['phase']} | {phase['status']} | {phase['criteria']}")
    lines.extend(["", "Principais modulos sugeridos:"])
    for name, count in sorted(plan["module_hint_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {name}: {count}")
    lines.extend(["", "Acoes sugeridas:"])
    for name, count in sorted(plan["action_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {name}: {count}")
    if plan["warnings"]:
        lines.extend(["", "Warnings:"])
        for warning in plan["warnings"]:
            lines.append(f"- {warning}")
    lines.extend(
        [
            "",
            "Regra de lancamento:",
            "- Para o piloto LAN, usar apenas inventario e dry-run.",
            "- Importacao em massa para banco fica bloqueada ate aprovacao do operador.",
            "- Nenhum arquivo da pasta secretaria deve entrar no Git.",
        ]
    )
    return "\n".join(lines)


def run_inventory(args: argparse.Namespace) -> None:
    inventory = build_inventory(
        Path(args.input),
        include_hash=args.hash,
        sample_limit=args.sample_limit,
    )
    paths = write_outputs(inventory, Path(args.output))
    batch_paths = write_batch_lists(Path(args.input), Path(args.output)) if args.write_file_lists else {}
    print(inventory_to_txt(inventory))
    for label, path in paths.items():
        print(f"{label}: {path}")
    for label, path in batch_paths.items():
        print(f"batch_{label}: {path}")


def run_plan(args: argparse.Namespace) -> None:
    inventory_path = Path(args.inventory)
    payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    samples = [SecretariaFileItem(**item) for item in payload.get("samples", [])]
    inventory = SecretariaInventory(
        schema_version=payload["schema_version"],
        generated_at=payload["generated_at"],
        source_root=payload["source_root"],
        total_files=payload["total_files"],
        total_bytes=payload["total_bytes"],
        extension_counts=payload["extension_counts"],
        top_folder_counts=payload["top_folder_counts"],
        module_hint_counts=payload["module_hint_counts"],
        action_counts=payload["action_counts"],
        samples=samples,
        warnings=payload.get("warnings", []),
    )
    plan = build_launch_plan(inventory)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    output.with_suffix(".txt").write_text(plan_to_txt(plan), encoding="utf-8")
    print(plan_to_txt(plan))
    print(f"JSON: {output}")
    print(f"TXT: {output.with_suffix('.txt')}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inventaria e planeja ingestao da pasta secretaria para o SISGES."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory_parser = subparsers.add_parser("inventario")
    inventory_parser.add_argument("--input", default=str(DEFAULT_INPUT))
    inventory_parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    inventory_parser.add_argument("--sample-limit", type=int, default=300)
    inventory_parser.add_argument(
        "--hash",
        action="store_true",
        help="Calcula SHA-256 das amostras. Evite em varreduras grandes se nao for necessario.",
    )
    inventory_parser.add_argument(
        "--no-file-lists",
        action="store_false",
        dest="write_file_lists",
        help="Nao gera CSVs completos por acao.",
    )
    inventory_parser.set_defaults(write_file_lists=True)
    inventory_parser.set_defaults(func=run_inventory)

    plan_parser = subparsers.add_parser("plano")
    plan_parser.add_argument(
        "--inventory",
        default=str(DEFAULT_OUTPUT / "inventario_secretaria.json"),
    )
    plan_parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT / "plano_ingestao_secretaria_lancamento.json"),
    )
    plan_parser.set_defaults(func=run_plan)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
