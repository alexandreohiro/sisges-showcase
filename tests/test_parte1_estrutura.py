"""Testes da estrutura textual da 1ª Parte (mês → título → referência → corpo)."""

from modules.compilador.application.folha_event_validation import (
    normalize_event_blocks,
    normalize_titulo,
    validate_ordem_referencias,
)
from modules.compilador.application.folha_models import EventBlock


def test_titulo_normaliza_hifen_para_travessao_preservando_hifens_internos():
    assert normalize_titulo("PLANO DE FÉRIAS - Alteração") == "PLANO DE FÉRIAS – Alteração"
    assert normalize_titulo("EXAME PRÉ-TAF - Resultado") == "EXAME PRÉ-TAF – Resultado"
    assert normalize_titulo("FOLHAS  DE   ALTERAÇÕES - Entrega") == "FOLHAS DE ALTERAÇÕES – Entrega"
    assert normalize_titulo("CURSOS E ESTÁGIOS") == "CURSOS E ESTÁGIOS"


def test_normalize_event_blocks_aplica_travessao_nos_titulos():
    events, _ = normalize_event_blocks(
        [
            EventBlock(
                mes="JANEIRO",
                titulo="ELOGIO INDIVIDUAL - Concessão",
                referencia="- a 3, BI Nº 5 :",
                corpo="Corpo do evento.",
            )
        ]
    )
    assert events[0].titulo == "ELOGIO INDIVIDUAL – Concessão"


def test_ordem_de_referencias_monotonica_por_mes():
    ok = [
        EventBlock(mes="JANEIRO", titulo="A", referencia="- a 3, BI Nº 5 :", corpo=""),
        EventBlock(mes="JANEIRO", titulo="B", referencia="- a 12, BI Nº 9 :", corpo=""),
        EventBlock(mes="FEVEREIRO", titulo="C", referencia="- a 2, BI Nº 21 :", corpo=""),
    ]
    assert validate_ordem_referencias(ok) == []

    quebrada = [
        EventBlock(mes="JANEIRO", titulo="A", referencia="- a 12, BI Nº 5 :", corpo=""),
        EventBlock(mes="JANEIRO", titulo="B", referencia="- a 3, BI Nº 9 :", corpo=""),
    ]
    warns = validate_ordem_referencias(quebrada)
    assert len(warns) == 1
    assert warns[0].startswith("WARN_ORDEM_EVENTOS_NAO_MONOTONICA:JANEIRO")
