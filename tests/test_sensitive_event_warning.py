from modules.compilador.application.folha_alteracoes_compiler import (
    EventBlock,
    detect_sensitive_event,
    normalize_event_blocks,
    sensitive_event_validations,
)


def test_detects_cpf():
    event = event_with_text("Atualizacao cadastral CPF 123.456.789-00.")

    assert "WARN_POSSIBLE_SENSITIVE_EVENT" in detect_sensitive_event(event)


def test_detects_arma_de_fogo():
    event = event_with_text("Autorizacao relacionada a arma de fogo e SIGMA.")

    assert "WARN_POSSIBLE_SENSITIVE_EVENT" in detect_sensitive_event(event)


def test_detects_beneficiario():
    event = event_with_text("DECLARACAO DE BENEFICIARIO - Atualizacao")

    assert "WARN_POSSIBLE_SENSITIVE_EVENT" in detect_sensitive_event(event)


def test_detects_pagamento():
    event = event_with_text("Informacao de pagamento em conta bancaria.")

    assert "WARN_REVIEW_BEFORE_SIGNATURE" in detect_sensitive_event(event)


def test_sensitive_detection_does_not_remove_event():
    event = event_with_text("DECLARACAO DE BENEFICIARIO - Atualizacao")
    events, _validations = normalize_event_blocks([event])

    assert len(events) == 1
    assert sensitive_event_validations(events) == [
        "WARN_POSSIBLE_SENSITIVE_EVENT",
        "WARN_REVIEW_BEFORE_SIGNATURE",
    ]


def event_with_text(text: str) -> EventBlock:
    return EventBlock(
        mes="JULHO",
        titulo=text,
        referencia="- a 1, BI Nº 1 :",
        corpo="Corpo preservado.",
    )
