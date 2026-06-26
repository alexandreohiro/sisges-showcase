from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
import zipfile


def main() -> None:
    parser = argparse.ArgumentParser(description="Empacota entrega final de Folhas de Alteracoes.")
    parser.add_argument("--input", required=True, help="Diretorio raiz da entrega final.")
    parser.add_argument("--output", required=True, help="Arquivo ZIP final.")
    args = parser.parse_args()

    input_root = Path(args.input)
    output_zip = Path(args.output)
    output_zip.parent.mkdir(parents=True, exist_ok=True)

    if (input_root / "FOLHAS_PRONTAS_ASSINATURA").exists():
        pack_revised_delivery(input_root, output_zip)
        return

    reports_dir = find_reports_dir(input_root)
    ready = read_classification(reports_dir / "folhas_prontas.csv")
    review = read_classification(reports_dir / "folhas_revisar.csv")
    blocked = read_classification(reports_dir / "folhas_bloqueadas.csv")
    hashes: dict[str, str] = {}
    written: set[str] = set()

    if output_zip.exists():
        output_zip.unlink()
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for section in ("FOLHAS_PRONTAS", "REVISAR", "BLOQUEADAS", "RELATORIOS", "LOGS"):
            write_text_once(archive, f"{section}/", "", written)
        add_classified_outputs(archive, "FOLHAS_PRONTAS", ready, input_root, hashes, written)
        add_classified_outputs(archive, "REVISAR", review, input_root, hashes, written)
        add_classified_outputs(archive, "BLOQUEADAS", blocked, input_root, hashes, written)
        add_reports(archive, input_root, reports_dir, hashes, written)
        add_logs(archive, input_root, ready, review, blocked, hashes, written)

    with zipfile.ZipFile(output_zip) as archive:
        bad = archive.testzip()
        entries = len(archive.namelist())
    if bad:
        raise SystemExit(f"Pacote final invalido. Entrada corrompida: {bad}")

    print("ENTREGA FINAL GERADA")
    print(f"Pacote: {output_zip}")
    print(f"Total de folhas: {len(ready) + len(review) + len(blocked)}")
    print(f"Prontas: {len(ready)}")
    print(f"Revisar: {len(review)}")
    print(f"Bloqueadas: {len(blocked)}")
    print(f"Entradas no ZIP: {entries}")
    print(f"Relatorio executivo: {input_root / 'RELATORIO_EXECUTIVO_SECRETARIA.txt'}")
    print(f"Checklist assinatura: {input_root / 'CHECKLIST_ASSINATURA.txt'}")
    print("Proxima acao: abrir CHECKLIST_ASSINATURA.txt e revisar folhas BLOQUEADAS antes da assinatura.")


def pack_revised_delivery(input_root: Path, output_zip: Path) -> None:
    hashes: dict[str, str] = {}
    written: set[str] = set()
    sections = (
        "FOLHAS_PRONTAS_ASSINATURA",
        "REVISAR_MANUALMENTE",
        "HOTFIX_APLICADO",
        "BLOQUEADAS",
        "RELATORIOS",
        "LOGS",
        "AMOSTRA_CONFERENCIA",
    )
    if output_zip.exists():
        output_zip.unlink()
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for section in sections:
            write_text_once(archive, f"{section}/", "", written)
        for section in sections:
            section_path = input_root / section
            if not section_path.exists():
                continue
            for source in sorted(section_path.rglob("*")):
                if source.is_file():
                    add_file(archive, source, source.relative_to(input_root), input_root, hashes, written)
        write_text_once(
            archive,
            "LOGS/hashes_outputs.json",
            json.dumps(hashes, ensure_ascii=False, indent=2),
            written,
        )
        resumo = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "input": str(input_root),
            "prontas_assinatura": count_leaf_folders(input_root / "FOLHAS_PRONTAS_ASSINATURA"),
            "revisar_manualmente": count_leaf_folders(input_root / "REVISAR_MANUALMENTE"),
            "hotfix_aplicado": count_leaf_folders(input_root / "HOTFIX_APLICADO"),
            "bloqueadas": count_leaf_folders(input_root / "BLOQUEADAS"),
        }
        write_text_once(archive, "LOGS/resumo_execucao_revisao.json", json.dumps(resumo, ensure_ascii=False, indent=2), written)

    with zipfile.ZipFile(output_zip) as archive:
        bad = archive.testzip()
        entries = len(archive.namelist())
    if bad:
        raise SystemExit(f"Pacote revisado invalido. Entrada corrompida: {bad}")

    print("PACOTE REVISADO GERADO")
    print(f"Pacote: {output_zip}")
    print(f"Prontas assinatura: {count_leaf_folders(input_root / 'FOLHAS_PRONTAS_ASSINATURA')}")
    print(f"Revisar manualmente: {count_leaf_folders(input_root / 'REVISAR_MANUALMENTE')}")
    print(f"Hotfix aplicado: {count_leaf_folders(input_root / 'HOTFIX_APLICADO')}")
    print(f"Bloqueadas: {count_leaf_folders(input_root / 'BLOQUEADAS')}")
    print(f"Entradas no ZIP: {entries}")


def count_leaf_folders(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.iterdir() if item.is_dir())


def find_reports_dir(input_root: Path) -> Path:
    candidates = [input_root / "RELATORIOS", input_root / "RELATORIO_GERAL_ENTREGA"]
    for candidate in candidates:
        if (candidate / "folhas_prontas.csv").exists():
            return candidate
    raise SystemExit("Relatorios de classificacao nao encontrados. Rode scripts.classificar_entrega_folhas primeiro.")


def read_classification(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def add_classified_outputs(
    archive: zipfile.ZipFile,
    section: str,
    rows: list[dict[str, str]],
    input_root: Path,
    hashes: dict[str, str],
    written: set[str],
) -> None:
    for row in rows:
        folder = Path(row["odt_path"]).parent
        semester = row.get("semestre_dir") or row.get("semestre") or "semestre"
        target_base = Path(section) / semester / folder.name
        for filename in ("folha_alteracoes.odt", "folha_alteracoes.pdf", "pacote.zip"):
            source = folder / filename
            if source.exists():
                add_file(archive, source, target_base / filename, input_root, hashes, written)


def add_reports(
    archive: zipfile.ZipFile,
    input_root: Path,
    reports_dir: Path,
    hashes: dict[str, str],
    written: set[str],
) -> None:
    report_files = [
        reports_dir / "folhas_prontas.csv",
        reports_dir / "folhas_revisar.csv",
        reports_dir / "folhas_bloqueadas.csv",
        reports_dir / "resumo_entrega.txt",
        reports_dir / "checklist_assinatura.txt",
        input_root / "RELATORIO_EXECUTIVO_SECRETARIA.txt",
        input_root / "CHECKLIST_ASSINATURA.txt",
    ]
    report_files.extend(reports_dir.glob("*.txt"))
    report_files.extend(reports_dir.glob("*.csv"))
    report_files.extend(reports_dir.glob("*.json"))
    for extra_name in ("indice_lote.csv", "pendencias_lote.json", "relatorio_missao_secretaria.txt", "RELATORIO_MISSAO_SECRETARIA.txt"):
        report_files.extend(input_root.rglob(extra_name))
    for source in sorted(set(report_files)):
        if source.exists():
            add_file(archive, source, Path("RELATORIOS") / source.name, input_root, hashes, written)


def add_logs(
    archive: zipfile.ZipFile,
    input_root: Path,
    ready: list[dict[str, str]],
    review: list[dict[str, str]],
    blocked: list[dict[str, str]],
    hashes: dict[str, str],
    written: set[str],
) -> None:
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input": str(input_root),
        "total": len(ready) + len(review) + len(blocked),
        "prontas": len(ready),
        "revisar": len(review),
        "bloqueadas": len(blocked),
    }
    write_text_once(archive, "LOGS/resumo_execucao.json", json.dumps(payload, ensure_ascii=False, indent=2), written)
    write_text_once(archive, "LOGS/hashes_outputs.json", json.dumps(hashes, ensure_ascii=False, indent=2), written)


def add_file(
    archive: zipfile.ZipFile,
    source: Path,
    target: Path,
    input_root: Path,
    hashes: dict[str, str],
    written: set[str],
) -> None:
    target_name = target.as_posix()
    if target_name in written:
        return
    archive.write(source, target_name)
    written.add(target_name)
    try:
        key = str(source.relative_to(input_root))
    except ValueError:
        key = str(source)
    hashes[key] = sha256_file(source)


def write_text_once(archive: zipfile.ZipFile, target: str, content: str, written: set[str]) -> None:
    if target in written:
        return
    archive.writestr(target, content)
    written.add(target)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
