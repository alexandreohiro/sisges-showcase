from __future__ import annotations

import csv
import json

from scripts.secretaria_alteracoes_dry_run import (
    classify_alteracao_row,
    run_assisted_review,
    run_dry_run,
)


def test_classify_date_range_filename() -> None:
    item = classify_alteracao_row(
        {
            "relative_path": "001 - ALTERAÇÕES/2025-07-01_2025-12-31_3sgt_alfa.pdf",
            "extension": ".pdf",
            "size_bytes": "123",
        },
    )

    assert item.year == 2025
    assert item.semester == 2
    assert item.posto_grad == "3 SGT"
    assert item.nome_hint == "ALFA"
    assert item.status == "READY_FOR_REFERENCE_DRY_RUN"


def test_classify_semester_filename() -> None:
    item = classify_alteracao_row(
        {
            "relative_path": "001 - ALTERAÇÕES/000 - ALTERAÇÕES SCANEADAS/CAP JANAINA 1° SEM 2020.pdf",
            "extension": ".pdf",
            "size_bytes": "456",
        },
    )

    assert item.year == 2020
    assert item.semester == 1
    assert item.posto_grad == "CAP"
    assert item.nome_hint == "JANAINA"


def test_classify_generic_list_requires_review() -> None:
    item = classify_alteracao_row(
        {
            "relative_path": "001 - ALTERAÇÕES/lista.pdf",
            "extension": ".pdf",
            "size_bytes": "789",
        },
    )

    assert item.status == "REVIEW_FILENAME_BEFORE_IMPORT"
    assert "WARN_MILITAR_NAME_NOT_INFERRED" in item.warnings
    assert "WARN_YEAR_NOT_INFERRED" in item.warnings


def test_classify_identity_year_semester_uses_parent_hint() -> None:
    item = classify_alteracao_row(
        {
            "relative_path": (
                "001 - ALTERAÇÕES/000 - ALTERAÇÕES SCANEADAS/"
                "2°_Sgt_ALBIGES/0119193050_2016_2_052001 ECT.pdf"
            ),
            "extension": ".pdf",
            "size_bytes": "123",
        },
    )

    assert item.year == 2016
    assert item.semester == 2
    assert item.posto_grad == "2 SGT"
    assert item.nome_hint == "ALBIGES"
    assert item.status == "READY_FOR_REFERENCE_DRY_RUN"


def test_classify_year_from_parent_path_when_filename_has_no_year() -> None:
    item = classify_alteracao_row(
        {
            "relative_path": "001 - ALTERAÇÕES/000 - ALTERAÇÕES SCANEADAS/2020/MAJ DA SILVA.pdf",
            "extension": ".pdf",
            "size_bytes": "456",
        },
    )

    assert item.year == 2020
    assert item.semester is None
    assert item.posto_grad == "MAJ"
    assert item.nome_hint == "DA SILVA"


def test_classify_identity_with_dash_digit_period() -> None:
    item = classify_alteracao_row(
        {
            "relative_path": (
                "001 - ALTERAÇÕES/000 - ALTERAÇÕES SCANEADAS/"
                "2001 a 2021 (scaneadas)/OFICIAIS/001- CEL/CEL- MAURICIO DE SOUZA/"
                "075917463-4_2008_1_022202.pdf"
            ),
            "extension": ".pdf",
            "size_bytes": "789",
        },
    )

    assert item.year == 2008
    assert item.semester == 1


def test_classify_semester_from_path_folder() -> None:
    item = classify_alteracao_row(
        {
            "relative_path": (
                "001 - ALTERAÇÕES/000 - ALTERAÇÕES SCANEADAS/"
                "Alterações 1° Sem 2020 OFICIAIS/CAP TESTE.pdf"
            ),
            "extension": ".pdf",
            "size_bytes": "789",
        },
    )

    assert item.year == 2020
    assert item.semester == 1
    assert item.posto_grad == "CAP"


def test_range_folder_does_not_become_document_year() -> None:
    item = classify_alteracao_row(
        {
            "relative_path": (
                "001 - ALTERAÇÕES/000 - ALTERAÇÕES SCANEADAS/"
                "2001 a 2021 (scaneadas)/OFICIAIS/001- CEL/CEL- MAURICIO DE SOUZA/"
                "20200608153200766.pdf"
            ),
            "extension": ".pdf",
            "size_bytes": "789",
        },
    )

    assert item.year is None
    assert "WARN_YEAR_NOT_INFERRED" in item.warnings


def test_numeric_scan_uses_parent_identity_without_period() -> None:
    item = classify_alteracao_row(
        {
            "relative_path": (
                "001 - ALTERAÇÕES/000 - ALTERAÇÕES SCANEADAS/"
                "2001 a 2021 (scaneadas)/OFICIAIS/001- CEL/CEL- MAURICIO DE SOUZA/"
                "20200608153200766.pdf"
            ),
            "extension": ".pdf",
            "size_bytes": "789",
        },
    )

    assert item.year is None
    assert item.semester is None
    assert item.posto_grad == "CEL"
    assert item.nome_hint == "MAURICIO DE SOUZA"
    assert "WARN_POSTO_GRAD_NOT_INFERRED" not in item.warnings


def test_loose_semester_before_year_removal() -> None:
    item = classify_alteracao_row(
        {
            "relative_path": "001 - ALTERAÇÕES/000 - ALTERAÇÕES SCANEADAS/ESCANEADAS/2° SGT EVERALDO 1° 2019.pdf",
            "extension": ".pdf",
            "size_bytes": "789",
        },
    )

    assert item.year == 2019
    assert item.semester == 1
    assert item.posto_grad == "2 SGT"
    assert item.nome_hint == "EVERALDO"


def test_run_dry_run_writes_reports(tmp_path) -> None:
    input_csv = tmp_path / "lote.csv"
    with input_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["relative_path", "extension", "size_bytes"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "relative_path": "001 - ALTERAÇÕES/2025-07-01_2025-12-31_2sgt_beatriz.pdf",
                "extension": ".pdf",
                "size_bytes": "100",
            },
        )

    result = run_dry_run(input_csv, tmp_path / "out")

    assert result["total_items"] == 1
    assert result["status_counts"]["READY_FOR_REFERENCE_DRY_RUN"] == 1
    payload = json.loads((tmp_path / "out" / "dry_run_alteracoes_001.json").read_text("utf-8"))
    assert payload["items"][0]["posto_grad"] == "2 SGT"


def test_run_assisted_review_groups_by_semester_and_priority(tmp_path) -> None:
    input_csv = tmp_path / "lote.csv"
    with input_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["relative_path", "extension", "size_bytes"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "relative_path": "001 - ALTERAÇÕES/2025-07-01_2025-12-31_2sgt_beatriz.pdf",
                "extension": ".pdf",
                "size_bytes": "100",
            },
        )
        writer.writerow(
            {
                "relative_path": "001 - ALTERAÇÕES/lista.pdf",
                "extension": ".pdf",
                "size_bytes": "200",
            },
        )

    dry_run = run_dry_run(input_csv, tmp_path / "dry")
    review = run_assisted_review(tmp_path / "dry" / "dry_run_alteracoes_001.json", tmp_path / "review")

    assert review["total_items"] == 2
    assert review["group_counts"]["2025_2sem"] == 1
    assert review["group_counts"]["SEM_PERIODO"] == 1
    assert review["priority_counts"]["LOW"] == 1
    assert review["priority_counts"]["HIGH"] == 1
    assert (tmp_path / "review" / "revisar_nome_nao_identificado.csv").exists()
    assert (tmp_path / "review" / "por_semestre" / "2025_2sem.csv").exists()
    assert dry_run["total_items"] == 2


def test_assisted_review_separates_normative_and_timestamp_scans(tmp_path) -> None:
    input_csv = tmp_path / "lote.csv"
    with input_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["relative_path", "extension", "size_bytes"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "relative_path": (
                    "001 - ALTERAÇÕES/000 - Legislação/"
                    "FOLHAS DE ALTERAÇÕES - PORTARIA_184-DGP_12-08-2013.pdf"
                ),
                "extension": ".pdf",
                "size_bytes": "100",
            },
        )
        writer.writerow(
            {
                "relative_path": (
                    "001 - ALTERAÇÕES/000 - ALTERAÇÕES SCANEADAS/"
                    "ESCANEADAS/20250130083147500.pdf"
                ),
                "extension": ".pdf",
                "size_bytes": "200",
            },
        )

    dry_run = run_dry_run(input_csv, tmp_path / "dry")
    review = run_assisted_review(tmp_path / "dry" / "dry_run_alteracoes_001.json", tmp_path / "review")

    assert review["source_kind_counts"]["DOCUMENTO_NORMATIVO"] == 1
    assert review["source_kind_counts"]["ESCANEAMENTO_TIMESTAMP"] == 1
    assert (tmp_path / "review" / "revisar_documento_normativo_ou_generico.csv").exists()
    assert (tmp_path / "review" / "revisar_escaneamento_sem_periodo.csv").exists()
    assert dry_run["total_items"] == 2
