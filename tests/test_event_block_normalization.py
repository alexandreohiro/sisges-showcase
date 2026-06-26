from modules.compilador.application.folha_alteracoes_compiler import (
    EventBlock,
    normalize_event_blocks,
)


def test_recovers_title_glued_to_body():
    events, validations = normalize_event_blocks(
        [
            EventBlock(
                mes="JULHO",
                titulo="",
                referencia="- a 1, BI Nº 1 :",
                corpo="TESTE DE AVALIACAO FISICA - Resultado\nMilitar realizou o TAF.",
            )
        ]
    )

    assert events[0].titulo == "TESTE DE AVALIACAO FISICA - Resultado"
    assert "Militar realizou o TAF." in events[0].corpo
    assert "OK_EVENT_TITLE_RECOVERED" in validations


def test_splits_body_when_next_title_and_reference_are_found():
    events, validations = normalize_event_blocks(
        [
            EventBlock(
                mes="JULHO",
                titulo="EVENTO ORIGINAL",
                referencia="- a 1, BI Nº 1 :",
                corpo=(
                    "Corpo do evento original.\n"
                    "TESTE DE AVALIACAO FISICA - Resultado\n"
                    "- a 2, BI Nº 2 :\n"
                    "Corpo do segundo evento."
                ),
            )
        ]
    )

    assert len(events) == 2
    assert events[1].titulo == "TESTE DE AVALIACAO FISICA - Resultado"
    assert events[1].referencia == "- a 2, BI Nº 2 :"
    assert "OK_EVENT_BODY_SPLIT_RECOVERED" in validations


def test_warns_when_title_cannot_be_recovered():
    events, validations = normalize_event_blocks(
        [
            EventBlock(
                mes="JULHO",
                titulo="",
                referencia="- a 1, BI Nº 1 :",
                corpo="texto comum sem linha de titulo",
            )
        ]
    )

    assert events[0].titulo == ""
    assert "WARN_EVENT_TITLE_MISSING" in validations
