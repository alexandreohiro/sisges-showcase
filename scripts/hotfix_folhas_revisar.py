from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


HOTFIX_WARNINGS = {
    "WARN_EVENT_TITLE_MISSING",
    "WARN_TABLE_UNREPAIRED",
    "WARN_QMS_NAO_RECONHECIDO",
    "WARN_ASSINATURA_NAO_CONFIRMADA",
    "WARN_FORMATACAO_DIVERGENTE",
    "WARN_TEMPLATE_STYLE_PARTIAL",
}


@dataclass(slots=True)
class HotfixResult:
    militar: str
    identidade: str
    folder: str
    warnings: str
    status: str
    acao: str
    observacao: str


def main() -> None:
    parser = argparse.ArgumentParser(description="Aplica hotfix automatico conservador em Folhas para revisar.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--modelo", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    input_root = resolve_input_root(Path(args.input))
    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)
    results: list[HotfixResult] = []

    for folder in discover_folders(input_root):
        variables = read_json(folder / "variables.json")
        validation = read_text(folder / "validacao.txt")
        militar = variables.get("militar") or {}
        warnings = extract_codes(validation, "WARN_")
        hotfixable = sorted(set(warnings) & HOTFIX_WARNINGS)
        if not hotfixable:
            continue
        # Nesta etapa final, nao reescrevemos ODT aceitavel sem regra segura.
        # O caso fica rastreado para revisao manual sem perder a versao gerada.
        results.append(
            HotfixResult(
                militar=str(militar.get("nome_completo") or ""),
                identidade=str(militar.get("identidade") or ""),
                folder=str(folder),
                warnings=";".join(hotfixable),
                status="NAO_APLICADO",
                acao="REVISAR_MANUALMENTE",
                observacao="Hotfix automatico conservador nao aplicado: exige decisao humana para titulo/tabela/QMS/assinatura.",
            )
        )

    write_outputs(output_root, results, args.modelo)
    print("HOTFIX FINAL AVALIADO")
    print(f"Fonte: {input_root}")
    print(f"Casos com hotfix requerido: {len(results)}")
    print("Hotfix aplicado: 0")
    print(f"Relatorio: {output_root / 'hotfix_folhas_revisar.csv'}")


def resolve_input_root(input_path: Path) -> Path:
    if input_path.exists() and any(input_path.rglob("variables.json")):
        return input_path
    fallback = input_path.parent / "2025_2sem"
    if fallback.exists():
        return fallback
    raise SystemExit(f"Entrada sem folhas revisaveis: {input_path}")


def discover_folders(root: Path) -> list[Path]:
    return sorted(path.parent for path in root.rglob("variables.json") if (path.parent / "validacao.txt").exists())


def extract_codes(text: str, prefix: str) -> list[str]:
    codes: list[str] = []
    for line in text.splitlines():
        stripped = line.strip().lstrip("-").strip()
        token = stripped.split(":", 1)[0].split()[0] if stripped else ""
        if token.startswith(prefix):
            codes.append(token)
    return codes


def write_outputs(output_root: Path, results: list[HotfixResult], modelo: str) -> None:
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "modelo": modelo,
        "hotfix_requerido": len(results),
        "hotfix_aplicado": 0,
        "items": [asdict(item) for item in results],
    }
    (output_root / "hotfix_folhas_revisar.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output_root / "hotfix_folhas_revisar.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = list(asdict(results[0]).keys()) if results else [
            "militar",
            "identidade",
            "folder",
            "warnings",
            "status",
            "acao",
            "observacao",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in results:
            writer.writerow(asdict(item))
    lines = [
        "RELATORIO DE HOTFIX DAS FOLHAS EM REVISAO",
        f"Gerado em: {payload['generated_at']}",
        f"Modelo: {modelo}",
        f"Hotfix requerido: {len(results)}",
        "Hotfix aplicado: 0",
        "",
        "Itens mantidos para revisao manual:",
    ]
    lines.extend(f"- {item.militar} ({item.identidade}): {item.warnings}" for item in results)
    (output_root / "hotfix_folhas_revisar.txt").write_text("\n".join(lines), encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


if __name__ == "__main__":
    main()
