from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest

from scripts.secretaria_operacional import file_sha256
from scripts.secretaria_release import create_release, release_summary, validate_release


def test_cria_release_em_diretorio_temporario(tmp_path: Path) -> None:
    package = create_package_and_artifacts(tmp_path)

    result = create_release(tmp_path, "secretaria_folhas_2025_revisado", package)

    release_dir = Path(result["release_dir"])
    assert release_dir.exists()
    assert (release_dir / "PACOTE_ENTREGA_SECRETARIA_REVISADO.zip").exists()
    assert (release_dir / "RELEASE_MANIFEST.json").exists()
    assert (release_dir / "README_RELEASE_OPERACIONAL.txt").exists()


def test_valida_pacote_zip_da_release(tmp_path: Path) -> None:
    package = create_package_and_artifacts(tmp_path)
    result = create_release(tmp_path, "secretaria_folhas_2025_revisado", package)

    validation = validate_release(Path(result["release_dir"]))

    assert validation["status"] == "OK"
    assert validation["zip_integro"] is True
    assert validation["sha256_ok"] is True


def test_detecta_sha_divergente(tmp_path: Path) -> None:
    package = create_package_and_artifacts(tmp_path)
    result = create_release(tmp_path, "secretaria_folhas_2025_revisado", package)
    release_dir = Path(result["release_dir"])
    (release_dir / "PACOTE_ENTREGA_SECRETARIA_REVISADO.zip.sha256").write_text(
        "0" * 64 + "  PACOTE_ENTREGA_SECRETARIA_REVISADO.zip\n",
        encoding="utf-8",
    )

    validation = validate_release(release_dir)

    assert validation["status"] == "ERRO"
    assert validation["sha256_ok"] is False


def test_gera_manifesto_e_readme(tmp_path: Path) -> None:
    package = create_package_and_artifacts(tmp_path)

    result = create_release(tmp_path, "secretaria_folhas_2025_revisado", package)
    manifest = json.loads((Path(result["release_dir"]) / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    readme = (Path(result["release_dir"]) / "README_RELEASE_OPERACIONAL.txt").read_text(encoding="utf-8")

    assert manifest["nome_release"] == "secretaria_folhas_2025_revisado"
    assert manifest["folhas_prontas_assinatura"] == 1
    assert "Não reprocessar" in readme


def test_resumo_nao_quebra(tmp_path: Path) -> None:
    package = create_package_and_artifacts(tmp_path)
    result = create_release(tmp_path, "secretaria_folhas_2025_revisado", package)

    summary = release_summary(Path(result["release_dir"]))

    assert summary["validation"]["status"] == "OK"
    assert summary["manifest"]["sha256_pacote"]


def test_falha_clara_se_pacote_nao_existe(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        create_release(tmp_path, "secretaria_folhas_2025_revisado", tmp_path / "data/output/ausente.zip")

    assert "Pacote principal não existe" in str(exc.value)


def create_package_and_artifacts(root: Path) -> Path:
    output = root / "data/output"
    output.mkdir(parents=True, exist_ok=True)
    package = output / "PACOTE_ENTREGA_SECRETARIA_REVISADO.zip"
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("FOLHAS_PRONTAS_ASSINATURA/militar/folha_alteracoes.odt", "odt")
        archive.writestr("FOLHAS_PRONTAS_ASSINATURA/militar/folha_alteracoes.pdf", "pdf")
        archive.writestr("REVISAR_MANUALMENTE/revisar/folha_alteracoes.odt", "odt")
        archive.writestr("REVISAR_MANUALMENTE/revisar/folha_alteracoes.pdf", "pdf")
        archive.writestr("BLOQUEADAS/", "")
        archive.writestr("RELATORIOS/RELATORIO_REVISAO_FINAL.txt", "relatorio")
        archive.writestr("RELATORIOS/CHECKLIST_ASSINATURA_REVISADO.txt", "checklist")
        archive.writestr("LOGS/hashes_outputs.json", "{}")
        archive.writestr("AMOSTRA_CONFERENCIA/checklist_amostra.txt", "amostra")
        archive.writestr("FOLHAS_PRONTAS_ASSINATURA/militar/validacao.txt", "OK_ODT_VALID")
        archive.writestr("FOLHAS_PRONTAS_ASSINATURA/militar/justificativa.txt", "justificativa")
        archive.writestr("FOLHAS_PRONTAS_ASSINATURA/militar/variables.json", "{}")
        archive.writestr("FOLHAS_PRONTAS_ASSINATURA/militar/compiler_run.json", "{}")
    sha = file_sha256(package)
    (package.with_suffix(package.suffix + ".sha256")).write_text(
        f"{sha}  {package.name}\n",
        encoding="utf-8",
    )
    for name in [
        "diagnostico_operacional_sisges.json",
        "diagnostico_operacional_sisges.txt",
        "VALIDACAO_PACOTE_REVISADO.json",
        "VALIDACAO_PACOTE_REVISADO.txt",
        "VALIDACAO_DOCUMENTACAO_OPERACIONAL.json",
        "VALIDACAO_DOCUMENTACAO_OPERACIONAL.txt",
        "PENDENCIAS_OPERACIONAIS_SECRETARIA.csv",
        "PENDENCIAS_OPERACIONAIS_SECRETARIA.json",
        "PENDENCIAS_OPERACIONAIS_SECRETARIA.txt",
        "CHECKLIST_FINAL_ASSINATURA_SECRETARIA.csv",
        "CHECKLIST_FINAL_ASSINATURA_SECRETARIA.txt",
        "REGISTRO_ENTREGA_SECRETARIA.json",
        "REGISTRO_ENTREGA_SECRETARIA.txt",
    ]:
        (output / name).write_text("x\n", encoding="utf-8")
    (output / "PENDENCIAS_OPERACIONAIS_SECRETARIA.csv").write_text("codigo\nWARN\n", encoding="utf-8")
    return package
