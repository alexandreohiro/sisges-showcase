from __future__ import annotations

from pathlib import Path

from scripts.secretaria_dataset import (
    build_inventory,
    module_hint_for,
    normalize_extension,
    safe_batch_name,
)


def test_secretaria_dataset_maps_known_folders() -> None:
    assert module_hint_for("001 - ALTERAÇÕES") == "folhas_alteracoes_compilador"
    assert module_hint_for("014 - LEGISLAÇÃO") == "legislacao_documentos"
    assert module_hint_for("020 - POP") == "pop_ajuda_operacional"
    assert module_hint_for("022 - CARTA DE RECOMENDAÇÃO") == "carta_recomendacao_declaracoes"


def test_secretaria_dataset_normalizes_missing_extension() -> None:
    assert normalize_extension(Path("arquivo")) == "[sem_extensao]"
    assert normalize_extension(Path("arquivo.PDF")) == ".pdf"


def test_secretaria_dataset_inventory_does_not_require_real_files(tmp_path: Path) -> None:
    alteracoes = tmp_path / "001 - ALTERAÇÕES"
    legislacao = tmp_path / "014 - LEGISLAÇÃO"
    temp = tmp_path / "015 - PROTOCOLO"
    alteracoes.mkdir()
    legislacao.mkdir()
    temp.mkdir()
    (alteracoes / "fonte.pdf").write_bytes(b"%PDF-1.4\n")
    (alteracoes / "modelo.odt").write_bytes(b"odt")
    (legislacao / "norma.docx").write_bytes(b"docx")
    (temp / "download.crdownload").write_bytes(b"tmp")

    inventory = build_inventory(tmp_path, sample_limit=10)

    assert inventory.total_files == 4
    assert inventory.extension_counts[".pdf"] == 1
    assert inventory.module_hint_counts["folhas_alteracoes_compilador"] == 2
    assert inventory.action_counts["IMPORTAR_COMO_REFERENCIA_COMPILADOR_DRY_RUN"] == 1
    assert inventory.action_counts["CLASSIFICAR_ODT_FONTE_OU_MODELO_DRY_RUN"] == 1
    assert inventory.action_counts["IGNORAR_ARTEFATO_TECNICO_OU_TEMPORARIO"] == 1


def test_secretaria_dataset_safe_batch_name() -> None:
    assert (
        safe_batch_name("IMPORTAR_COMO_REFERENCIA_COMPILADOR_DRY_RUN")
        == "importar_como_referencia_compilador_dry_run"
    )
    assert safe_batch_name("REVISAR/MANUALMENTE") == "revisar_manualmente"
