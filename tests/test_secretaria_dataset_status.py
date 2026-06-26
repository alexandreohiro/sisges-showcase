from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

from modules.documents.application.secretaria_dataset_status import load_secretaria_dataset_status


def test_secretaria_dataset_status_reports_missing_inventory(tmp_path: Path) -> None:
    status = load_secretaria_dataset_status(tmp_path)

    assert status["available"] is False
    assert status["status"] == "INVENTARIO_AUSENTE"
    assert status["inventory"] is None
    assert status["operational_readiness"]["status"] == "BLOQUEADO"
    assert status["operational_readiness"]["can_lan_dry_run"] is False


def test_secretaria_dataset_status_compacts_inventory_and_plan(tmp_path: Path) -> None:
    (tmp_path / "lotes").mkdir()
    (tmp_path / "revisao_assistida_alteracoes").mkdir()
    (tmp_path / "revisao_assistida_alteracoes" / "por_semestre").mkdir()
    (tmp_path / "lotes" / "importar.csv").write_text("relative_path\nx.pdf\n", encoding="utf-8")
    (tmp_path / "inventario_secretaria.txt").write_text("inventario\n", encoding="utf-8")
    (tmp_path / "plano_ingestao_secretaria_lancamento.txt").write_text(
        "plano\n",
        encoding="utf-8",
    )
    (tmp_path / "revisao_assistida_alteracoes" / "por_semestre" / "2025_2sem.csv").write_text(
        "relative_path\nx.pdf\n",
        encoding="utf-8",
    )
    (tmp_path / "inventario_secretaria.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-05-28T00:00:00+00:00",
                "total_files": 10,
                "total_bytes": 1000,
                "extension_counts": {".pdf": 8},
                "top_folder_counts": {"001 - ALTERAÇÕES": 8},
                "module_hint_counts": {"folhas_alteracoes_compilador": 8},
                "action_counts": {"IMPORTAR_COMO_REFERENCIA_COMPILADOR_DRY_RUN": 8},
                "samples": [{"relative_path": "nao_deve_vazar.pdf"}],
                "warnings": ["WARN_EXTENSAO_NAO_MAPEADA"],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "plano_ingestao_secretaria_lancamento.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-05-28T00:00:00+00:00",
                "recommended_release_step": "PILOTO_LAN_COM_STAGING_SECRETARIA",
                "go_no_go": {"lan_pilot": "GO_COM_DRY_RUN"},
                "phases": [{"phase": "1_INVENTARIO", "status": "DONE"}],
                "module_hint_counts": {"folhas_alteracoes_compilador": 8},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "revisao_assistida_alteracoes" / "resumo_revisao_assistida_alteracoes.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-05-28T00:00:00+00:00",
                "total_items": 8,
                "priority_counts": {"LOW": 3, "HIGH": 5},
                "reason_counts": {"PERIODO_NAO_IDENTIFICADO": 5},
                "group_counts": {"SEM_PERIODO": 5, "2025_2sem": 3},
                "source_kind_counts": {
                    "ESCANEAMENTO_TIMESTAMP": 2,
                    "DOCUMENTO_NORMATIVO": 1,
                },
                "outputs": {
                    "all": "data/output/revisao.csv",
                    "por_semestre": str(tmp_path / "revisao_assistida_alteracoes" / "por_semestre"),
                },
                "items": [{"relative_path": "nao_deve_vazar.pdf"}],
            },
        ),
        encoding="utf-8",
    )

    status = load_secretaria_dataset_status(tmp_path)

    assert status["available"] is True
    assert status["inventory"]["total_files"] == 10
    assert "samples" not in status["inventory"]
    assert status["plan"]["go_no_go"]["lan_pilot"] == "GO_COM_DRY_RUN"
    assert status["assisted_review"]["priority_counts"]["HIGH"] == 5
    assert status["assisted_review"]["group_counts"]["SEM_PERIODO"] == 5
    assert status["assisted_review"]["source_kind_counts"]["ESCANEAMENTO_TIMESTAMP"] == 2
    assert status["assisted_review"]["semester_outputs"][0]["key"] == "2025_2sem"
    assert "items" not in status["assisted_review"]
    assert status["lots"][0]["filename"] == "importar.csv"
    assert status["reports"][0]["key"] == "inventario_txt"
    assert status["operational_readiness"]["status"] == "PRONTO_PARA_DRY_RUN_LAN"
    assert status["operational_readiness"]["can_lan_dry_run"] is True
    assert status["operational_readiness"]["warning_count"] >= 1
    assert any(
        check["key"] == "high_priority_review"
        for check in status["operational_readiness"]["checks"]
    )


def test_resolve_secretaria_review_output_path_uses_allowlisted_files(tmp_path: Path) -> None:
    from modules.documents.application.secretaria_dataset_status import (
        resolve_secretaria_review_output_path,
    )

    review_dir = tmp_path / "revisao_assistida_alteracoes"
    review_dir.mkdir()
    queue_path = review_dir / "revisao_assistida_alteracoes.csv"
    queue_path.write_text("relative_path,status\nx.pdf,READY\n", encoding="utf-8")
    (review_dir / "resumo_revisao_assistida_alteracoes.json").write_text(
        json.dumps({"outputs": {"all": str(queue_path)}}),
        encoding="utf-8",
    )

    resolved = resolve_secretaria_review_output_path("all", tmp_path)

    assert resolved == queue_path.resolve()
    assert resolve_secretaria_review_output_path("missing", tmp_path) is None


def test_resolve_secretaria_review_output_path_blocks_paths_outside_root(tmp_path: Path) -> None:
    from modules.documents.application.secretaria_dataset_status import (
        resolve_secretaria_review_output_path,
    )

    outside_path = tmp_path.parent / "fora.csv"
    outside_path.write_text("x\n", encoding="utf-8")
    review_dir = tmp_path / "revisao_assistida_alteracoes"
    review_dir.mkdir()
    (review_dir / "resumo_revisao_assistida_alteracoes.json").write_text(
        json.dumps({"outputs": {"outside": str(outside_path)}}),
        encoding="utf-8",
    )

    assert resolve_secretaria_review_output_path("outside", tmp_path) is None


def test_resolve_secretaria_semester_review_output_path_uses_period_key(tmp_path: Path) -> None:
    from modules.documents.application.secretaria_dataset_status import (
        resolve_secretaria_semester_review_output_path,
    )

    semester_dir = tmp_path / "revisao_assistida_alteracoes" / "por_semestre"
    semester_dir.mkdir(parents=True)
    queue_path = semester_dir / "2025_2sem.csv"
    queue_path.write_text("relative_path,status\nx.pdf,READY\n", encoding="utf-8")
    (tmp_path / "revisao_assistida_alteracoes" / "resumo_revisao_assistida_alteracoes.json").write_text(
        json.dumps({"outputs": {"por_semestre": str(semester_dir)}}),
        encoding="utf-8",
    )

    resolved = resolve_secretaria_semester_review_output_path("2025_2sem", tmp_path)

    assert resolved == queue_path.resolve()
    assert resolve_secretaria_semester_review_output_path("../2025_2sem", tmp_path) is None
    assert resolve_secretaria_semester_review_output_path("SEM_PERIODO", tmp_path) is None


def test_resolve_secretaria_lot_output_path_uses_safe_lot_name(tmp_path: Path) -> None:
    from modules.documents.application.secretaria_dataset_status import (
        resolve_secretaria_lot_output_path,
    )

    lots_dir = tmp_path / "lotes"
    lots_dir.mkdir()
    lot_path = lots_dir / "importar_como_referencia_compilador_dry_run.csv"
    lot_path.write_text("relative_path\nx.pdf\n", encoding="utf-8")

    resolved = resolve_secretaria_lot_output_path(
        "importar_como_referencia_compilador_dry_run",
        tmp_path,
    )

    assert resolved == lot_path.resolve()
    assert resolve_secretaria_lot_output_path("../inventario_secretaria", tmp_path) is None
    assert resolve_secretaria_lot_output_path("lote-com-hifen", tmp_path) is None


def test_resolve_secretaria_report_output_path_uses_report_allowlist(tmp_path: Path) -> None:
    from modules.documents.application.secretaria_dataset_status import (
        resolve_secretaria_report_output_path,
    )

    report_path = tmp_path / "inventario_secretaria.txt"
    report_path.write_text("inventario\n", encoding="utf-8")

    resolved = resolve_secretaria_report_output_path("inventario_txt", tmp_path)

    assert resolved == report_path.resolve()
    assert resolve_secretaria_report_output_path("inventario_secretaria", tmp_path) is None


def test_build_secretaria_audit_package_includes_allowlisted_artifacts(tmp_path: Path) -> None:
    from io import BytesIO

    from modules.documents.application.secretaria_dataset_status import (
        build_secretaria_audit_package,
    )

    (tmp_path / "inventario_secretaria.txt").write_text("inventario\n", encoding="utf-8")
    lots_dir = tmp_path / "lotes"
    lots_dir.mkdir()
    (lots_dir / "importar.csv").write_text("relative_path\nx.pdf\n", encoding="utf-8")
    review_dir = tmp_path / "revisao_assistida_alteracoes"
    semester_dir = review_dir / "por_semestre"
    semester_dir.mkdir(parents=True)
    review_csv = review_dir / "revisao_assistida_alteracoes.csv"
    semester_csv = semester_dir / "2025_2sem.csv"
    review_csv.write_text("relative_path\nx.pdf\n", encoding="utf-8")
    semester_csv.write_text("relative_path\nx.pdf\n", encoding="utf-8")
    (review_dir / "resumo_revisao_assistida_alteracoes.json").write_text(
        json.dumps(
            {
                "outputs": {
                    "all": str(review_csv),
                    "por_semestre": str(semester_dir),
                },
            },
        ),
        encoding="utf-8",
    )

    package = build_secretaria_audit_package(tmp_path)

    assert package is not None
    with ZipFile(BytesIO(package)) as zip_file:
        names = set(zip_file.namelist())
    assert "MANIFESTO_AUDITORIA_SECRETARIA.json" in names
    assert "RELATORIOS/inventario_txt/inventario_secretaria.txt" in names
    assert "LOTES/importar.csv" in names
    assert "REVISAO/all/revisao_assistida_alteracoes.csv" in names
    assert "REVISAO/POR_SEMESTRE/2025_2sem.csv" in names
