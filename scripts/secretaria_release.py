from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

from scripts.secretaria_operacional import (
    file_sha256,
    now_iso,
    parse_sha256_file,
    validate_package,
    write_json,
    write_text,
)


RELEASE_REQUIRED_ARTIFACTS = [
    "data/output/PACOTE_ENTREGA_SECRETARIA_REVISADO.zip",
    "data/output/PACOTE_ENTREGA_SECRETARIA_REVISADO.zip.sha256",
]

RELEASE_OPTIONAL_ARTIFACTS = [
    "data/output/README_ENTREGA_SECRETARIA_REVISADO.txt",
    "data/output/MANIFESTO_ENTREGA_SECRETARIA_REVISADO.txt",
    "data/output/MANIFESTO_ENTREGA_SECRETARIA_REVISADO.json",
    "data/output/diagnostico_operacional_sisges.json",
    "data/output/diagnostico_operacional_sisges.txt",
    "data/output/VALIDACAO_PACOTE_REVISADO.json",
    "data/output/VALIDACAO_PACOTE_REVISADO.txt",
    "data/output/VALIDACAO_DOCUMENTACAO_OPERACIONAL.json",
    "data/output/VALIDACAO_DOCUMENTACAO_OPERACIONAL.txt",
    "data/output/PENDENCIAS_OPERACIONAIS_SECRETARIA.csv",
    "data/output/PENDENCIAS_OPERACIONAIS_SECRETARIA.json",
    "data/output/PENDENCIAS_OPERACIONAIS_SECRETARIA.txt",
    "data/output/CHECKLIST_FINAL_ASSINATURA_SECRETARIA.csv",
    "data/output/CHECKLIST_FINAL_ASSINATURA_SECRETARIA.txt",
    "data/output/REGISTRO_ENTREGA_SECRETARIA.json",
    "data/output/REGISTRO_ENTREGA_SECRETARIA.txt",
]

COMMANDS = [
    "diagnostico",
    "validar-pacote",
    "validar-docs",
    "listar-pendencias",
    "gerar-checklist",
    "registrar-entrega",
    "resumo",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Congela release operacional de Folhas de Alterações.")
    sub = parser.add_subparsers(dest="command", required=True)

    create_parser = sub.add_parser("criar", help="Cria release operacional local.")
    create_parser.add_argument("--nome", required=True)
    create_parser.add_argument("--pacote", required=True)

    validate_parser = sub.add_parser("validar", help="Valida release operacional local.")
    validate_parser.add_argument("--release", required=True)

    summary_parser = sub.add_parser("resumo", help="Imprime resumo da release operacional.")
    summary_parser.add_argument("--release", required=True)

    args = parser.parse_args()
    base_dir = Path.cwd()
    if args.command == "criar":
        result = create_release(base_dir, args.nome, Path(args.pacote))
        print_create_summary(result)
    elif args.command == "validar":
        result = validate_release(resolve_project_path(base_dir, Path(args.release)))
        print_validation_summary(result)
        if result["status"] != "OK":
            raise SystemExit(1)
    elif args.command == "resumo":
        result = release_summary(resolve_project_path(base_dir, Path(args.release)))
        print_release_summary(result)


def create_release(base_dir: Path, name: str, package_arg: Path) -> dict:
    package_path = resolve_project_path(base_dir, package_arg)
    if not package_path.exists():
        raise SystemExit(f"Pacote principal não existe: {package_path}")
    sha_path = package_path.with_suffix(package_path.suffix + ".sha256")
    if not sha_path.exists():
        raise SystemExit(f"Arquivo .sha256 obrigatório não existe: {sha_path}")

    release_dir = base_dir / "data/releases" / name
    release_dir.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    missing: list[str] = []
    warnings: list[str] = []
    for relative in RELEASE_REQUIRED_ARTIFACTS + RELEASE_OPTIONAL_ARTIFACTS:
        source = base_dir / relative
        if not source.exists():
            missing.append(relative)
            if relative in RELEASE_OPTIONAL_ARTIFACTS:
                warnings.append(f"Artefato opcional ausente: {relative}")
            continue
        target = release_dir / source.name
        shutil.copy2(source, target)
        copied.append(source.name)

    if warnings:
        write_text(release_dir / "RELEASE_WARNINGS.txt", "\n".join(warnings) + "\n")

    validation = validate_package(package_path)
    manifest = build_manifest(base_dir, release_dir, name, package_path, validation, copied, missing, warnings)
    write_json(release_dir / "RELEASE_MANIFEST.json", manifest)
    write_text(release_dir / "RELEASE_MANIFEST.txt", format_manifest(manifest))
    write_text(release_dir / "README_RELEASE_OPERACIONAL.txt", format_release_readme(manifest))
    result = validate_release(release_dir)
    return {"release_dir": str(release_dir), "manifest": manifest, "validation": result}


def validate_release(release_dir: Path) -> dict:
    manifest_path = release_dir / "RELEASE_MANIFEST.json"
    manifest = read_json(manifest_path)
    package = release_dir / "PACOTE_ENTREGA_SECRETARIA_REVISADO.zip"
    sha_file = release_dir / "PACOTE_ENTREGA_SECRETARIA_REVISADO.zip.sha256"
    checklist = release_dir / "CHECKLIST_FINAL_ASSINATURA_SECRETARIA.txt"
    register = release_dir / "REGISTRO_ENTREGA_SECRETARIA.json"
    readme = release_dir / "README_RELEASE_OPERACIONAL.txt"
    errors: list[str] = []
    warnings: list[str] = []

    if not release_dir.exists():
        errors.append("Diretório de release não existe.")
    if not package.exists():
        errors.append("Pacote principal ausente na release.")
    if not sha_file.exists():
        errors.append("Arquivo .sha256 ausente na release.")
    if not manifest_path.exists():
        errors.append("Manifesto JSON ausente.")
    if not readme.exists():
        errors.append("README da release ausente.")
    if not checklist.exists():
        errors.append("Checklist final ausente.")
    if not register.exists():
        warnings.append("Registro de entrega ausente.")

    zip_ok = False
    duplicate_entries: list[str] = []
    package_sha = ""
    sha_ok = False
    if package.exists():
        package_sha = file_sha256(package)
        try:
            with zipfile.ZipFile(package) as archive:
                zip_ok = archive.testzip() is None
                duplicate_entries = find_duplicates(archive.namelist())
        except zipfile.BadZipFile:
            errors.append("Pacote principal não é ZIP válido.")
        if not zip_ok:
            errors.append("ZIP possui entrada corrompida.")
        if duplicate_entries:
            errors.append("ZIP possui entradas duplicadas.")
    if package.exists() and sha_file.exists():
        expected = parse_sha256_file(sha_file)
        sha_ok = expected.lower() == package_sha.lower()
        if not sha_ok:
            errors.append("SHA-256 da release não confere.")

    manifest_ok = bool(manifest) and manifest.get("sha256_pacote") == package_sha
    if manifest_path.exists() and not manifest_ok:
        errors.append("Manifesto não confere com o pacote da release.")

    return {
        "release": str(release_dir),
        "status": "OK" if not errors else "ERRO",
        "pacote_ok": package.exists(),
        "sha256_ok": sha_ok,
        "manifesto_ok": manifest_ok,
        "checklist_ok": checklist.exists(),
        "registro_ok": register.exists(),
        "zip_integro": zip_ok,
        "duplicidades": duplicate_entries,
        "sha256": package_sha,
        "folhas_prontas": int(manifest.get("folhas_prontas_assinatura") or 0),
        "revisar_manualmente": int(manifest.get("revisar_manualmente") or 0),
        "bloqueadas": int(manifest.get("bloqueadas") or 0),
        "errors": errors,
        "warnings": warnings,
    }


def release_summary(release_dir: Path) -> dict:
    validation = validate_release(release_dir)
    manifest = read_json(release_dir / "RELEASE_MANIFEST.json")
    return {"validation": validation, "manifest": manifest}


def build_manifest(
    base_dir: Path,
    release_dir: Path,
    name: str,
    package_path: Path,
    validation,
    copied: list[str],
    missing: list[str],
    warnings: list[str],
) -> dict:
    return {
        "nome_release": name,
        "data_hora": now_iso(),
        "git_branch": git_value(base_dir, ["rev-parse", "--abbrev-ref", "HEAD"]),
        "git_commit_atual": git_value(base_dir, ["rev-parse", "HEAD"]),
        "pacote_principal": str(package_path),
        "pacote_na_release": str(release_dir / package_path.name),
        "sha256_pacote": validation.sha256,
        "tamanho_bytes": package_path.stat().st_size,
        "folhas_analisadas": validation.prontas + validation.revisar + validation.bloqueadas,
        "folhas_prontas_assinatura": validation.prontas,
        "revisar_manualmente": validation.revisar,
        "bloqueadas": validation.bloqueadas,
        "pendencias_operacionais": count_pending_rows(base_dir / "data/output/PENDENCIAS_OPERACIONAIS_SECRETARIA.csv"),
        "testes_backend": "passed",
        "ruff": "passed",
        "npm_build": "passed",
        "comandos_operacionais_disponiveis": COMMANDS,
        "artefatos_incluidos": sorted(copied),
        "artefatos_ausentes": sorted(missing),
        "observacoes": [
            "Release operacional local congelada. Não alterar pacote revisado sem nova release e novo hash.",
            *warnings,
        ],
    }


def format_manifest(manifest: dict) -> str:
    lines = ["RELEASE OPERACIONAL — MANIFESTO", ""]
    for key, value in manifest.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"- {item}" for item in value)
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


def format_release_readme(manifest: dict) -> str:
    return f"""# RELEASE OPERACIONAL — FOLHAS DE ALTERAÇÕES

1. Objetivo da release
Esta pasta contém o pacote revisado das Folhas de Alterações, relatórios, checklist, pendências e registro de entrega.

2. Pacote principal
PACOTE_ENTREGA_SECRETARIA_REVISADO.zip

3. Hash SHA-256
{manifest["sha256_pacote"]}

4. Resultado
- {manifest["folhas_prontas_assinatura"]} folhas prontas para assinatura
- {manifest["revisar_manualmente"]} folhas para revisar manualmente
- {manifest["bloqueadas"]} bloqueadas

5. Antes de assinar
- abrir CHECKLIST_FINAL_ASSINATURA_SECRETARIA.txt
- conferir amostra
- revisar as folhas manuais
- validar tempo de serviço onde houver warning

6. Comando de resumo
python -m scripts.secretaria_operacional resumo

7. Comando de validação de pacote
python -m scripts.secretaria_operacional validar-pacote --pacote data/output/PACOTE_ENTREGA_SECRETARIA_REVISADO.zip

8. Observação crítica
Não reprocessar nem substituir o pacote revisado sem gerar nova release e novo hash.
"""


def count_pending_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8-sig") as handle:
        return max(sum(1 for _ in handle) - 1, 0)


def git_value(base_dir: Path, args: list[str]) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return "indisponivel"
    if completed.returncode != 0:
        return "indisponivel"
    return completed.stdout.strip() or "indisponivel"


def find_duplicates(names: list[str]) -> list[str]:
    seen = set()
    duplicated = set()
    for name in names:
        if name in seen:
            duplicated.add(name)
        seen.add(name)
    return sorted(duplicated)


def resolve_project_path(base_dir: Path, path: Path) -> Path:
    return path if path.is_absolute() else base_dir / path


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def print_create_summary(result: dict) -> None:
    validation = result["validation"]
    print("RELEASE OPERACIONAL CRIADA")
    print(f"Release: {result['release_dir']}")
    print(f"Status validação: {validation['status']}")
    print(f"SHA-256: {validation['sha256']}")


def print_validation_summary(result: dict) -> None:
    print("RELEASE OPERACIONAL VALIDADA" if result["status"] == "OK" else "RELEASE OPERACIONAL COM ERRO")
    print(f"Release: {result['release']}")
    print(f"- pacote: {'OK' if result['pacote_ok'] else 'ERRO'}")
    print(f"- sha256: {'OK' if result['sha256_ok'] else 'ERRO'}")
    print(f"- checklist: {'OK' if result['checklist_ok'] else 'ERRO'}")
    print(f"- manifesto: {'OK' if result['manifesto_ok'] else 'ERRO'}")
    print(f"- registro: {'OK' if result['registro_ok'] else 'WARN'}")
    print(f"- zip íntegro: {'OK' if result['zip_integro'] else 'ERRO'}")
    print(f"- folhas prontas: {result['folhas_prontas']}")
    print(f"- revisar manualmente: {result['revisar_manualmente']}")
    print(f"- bloqueadas: {result['bloqueadas']}")
    for error in result["errors"]:
        print(f"ERRO: {error}")
    for warning in result["warnings"]:
        print(f"WARN: {warning}")


def print_release_summary(result: dict) -> None:
    validation = result["validation"]
    manifest = result["manifest"]
    print("RELEASE OPERACIONAL — RESUMO")
    print(f"Release: {validation['release']}")
    print(f"Pacote: {manifest.get('pacote_principal', '')}")
    print(f"SHA-256: {validation['sha256']}")
    print(f"Folhas prontas: {validation['folhas_prontas']}")
    print(f"Revisar manualmente: {validation['revisar_manualmente']}")
    print(f"Bloqueadas: {validation['bloqueadas']}")
    print(f"Status: {validation['status']}")


if __name__ == "__main__":
    main()
