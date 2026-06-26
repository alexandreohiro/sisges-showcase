from __future__ import annotations

from pathlib import Path

from scripts.parse_parte1_events import (
    SCHEMA_VERSION,
    parse_parte1_paragraphs,
    parse_parte1_source,
)


def test_parse_reference_body_nested_function() -> None:
    result = parse_parte1_paragraphs(
        [
            "JULHO:",
            "INSTALACAO - Concessao",
            "- a 1, BI No 50:",
            "De acordo com o inciso I do art. 454.",
            "AGOSTO:",
            "Sem alteracoes.",
        ],
        semestre="2",
    )

    assert result.schema_version == SCHEMA_VERSION
    assert result.errors == []
    assert result.meses[0].mes == "JULHO"
    assert result.meses[0].eventos[0].titulo == "INSTALACAO - Concessao"
    assert result.meses[0].eventos[0].bi.referencia == "- a 1, BI No 50:"
    assert result.meses[0].eventos[0].bi.corpo == "De acordo com o inciso I do art. 454."
    assert result.meses[1].mes == "AGOSTO"
    assert result.meses[1].sem_alteracoes is True


def test_parse_multiple_events_same_month() -> None:
    result = parse_parte1_paragraphs(
        [
            "JULHO:",
            "INSTALACAO - Concessao",
            "- a 1, BI No 50:",
            "Corpo um.",
            "EQUIPE DE PLANEJAMENTO DA CONTRATACAO - Nomeacao",
            "- a 8, BI No 52:",
            "Corpo dois.",
        ],
        semestre="2",
    )

    events = result.meses[0].eventos

    assert [event.titulo for event in events] == [
        "INSTALACAO - Concessao",
        "EQUIPE DE PLANEJAMENTO DA CONTRATACAO - Nomeacao",
    ]
    assert events[1].bi.referencia == "- a 8, BI No 52:"
    assert events[1].bi.corpo == "Corpo dois."


def test_parse_empty_month_sem_alteracoes() -> None:
    result = parse_parte1_paragraphs(["DEZEMBRO:", "Sem Alteracao."], semestre="2")

    month = result.meses[0]

    assert month.mes == "DEZEMBRO"
    assert month.sem_alteracoes is True
    assert month.eventos == []
    assert month.warnings == ["OK_EMPTY_MONTH"]


def test_parse_sensitive_warning_does_not_remove_event() -> None:
    result = parse_parte1_paragraphs(
        [
            "AGOSTO:",
            "DECLARACAO DE BENEFICIARIO - Atualizacao",
            "- a 2, BI No 51:",
            "CPF 000.000.000-00 informado para conferencia.",
        ],
        semestre="2",
    )

    event = result.meses[0].eventos[0]

    assert event.bi.corpo == "CPF 000.000.000-00 informado para conferencia."
    assert "WARN_POSSIBLE_SENSITIVE_EVENT" in event.warnings
    assert "WARN_REVIEW_BEFORE_SIGNATURE" in event.warnings


def test_parse_reference_without_title_generates_warning() -> None:
    result = parse_parte1_paragraphs(
        [
            "SETEMBRO:",
            "- a 10, BI No 60:",
            "Corpo sem titulo recuperavel.",
        ],
        semestre="2",
    )

    event = result.meses[0].eventos[0]

    assert event.titulo == ""
    assert event.bi.referencia == "- a 10, BI No 60:"
    assert "WARN_EVENT_TITLE_MISSING" in event.warnings


def test_parse_does_not_treat_body_hyphen_as_title() -> None:
    result = parse_parte1_paragraphs(
        [
            "OUTUBRO:",
            "PROCESSO ADMINISTRATIVO - Instauracao",
            "- a 9, BI No 70:",
            "Corpo do evento - com hifen interno e texto normal.",
            "NOVEMBRO:",
        ],
        semestre="2",
    )

    event = result.meses[0].eventos[0]

    assert event.titulo == "PROCESSO ADMINISTRATIVO - Instauracao"
    assert event.bi.corpo == "Corpo do evento - com hifen interno e texto normal."
    assert result.meses[1].mes == "NOVEMBRO"


def test_parse_does_not_treat_table_label_as_event_title() -> None:
    result = parse_parte1_paragraphs(
        [
            "JULHO:",
            "TESTE DE AVALIACAO FISICA - Nomeacao",
            "- a 10, BI No 53:",
            "Designo para compor comissao.",
            "Membro",
            "Nome: MILITAR TESTE",
        ],
        semestre="2",
    )

    events = result.meses[0].eventos

    assert len(events) == 1
    assert events[0].titulo == "TESTE DE AVALIACAO FISICA - Nomeacao"
    assert "Membro" in events[0].bi.corpo
    assert "Nome: MILITAR TESTE" in events[0].bi.corpo
    assert "WARN_EVENT_REFERENCE_MISSING" not in events[0].warnings


def test_parse_does_not_treat_numbered_body_line_as_event_title() -> None:
    result = parse_parte1_paragraphs(
        [
            "SETEMBRO:",
            "PROCESSO ADMINISTRATIVO - Abertura",
            "- a 11, BI No 61:",
            "Considerando os fatos narrados.",
            "1. Tendo tomado conhecimento dos fatos, determino apuracao.",
            "2. O presente procedimento tem finalidade administrativa.",
        ],
        semestre="2",
    )

    events = result.meses[0].eventos

    assert len(events) == 1
    assert "1. Tendo tomado conhecimento" in events[0].bi.corpo
    assert "2. O presente procedimento" in events[0].bi.corpo
    assert "WARN_EVENT_REFERENCE_MISSING" not in events[0].warnings


def test_parse_from_txt_source_adds_required_months(tmp_path: Path) -> None:
    source = tmp_path / "2025-07-01_2025-12-31_sten_teste.txt"
    source.write_text(
        "\n".join(
            [
                "Cabecalho ignoravel",
                "JULHO:",
                "INSTALACAO - Concessao",
                "- a 1, BI No 50:",
                "Corpo do evento.",
                "2a PARTE",
            ]
        ),
        encoding="utf-8",
    )

    result = parse_parte1_source(source, semestre="2")

    assert [month.mes for month in result.meses] == [
        "JULHO",
        "AGOSTO",
        "SETEMBRO",
        "OUTUBRO",
        "NOVEMBRO",
        "DEZEMBRO",
    ]
    assert result.meses[0].eventos[0].titulo == "INSTALACAO - Concessao"
    assert any(warning.startswith("OK_EMPTY_MONTHS_FILLED:") for warning in result.warnings)
