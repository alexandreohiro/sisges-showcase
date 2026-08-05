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


def test_mes_vazio_da_referencia_nao_vira_corpo(tmp_path):
    """"ABRIL: Sem Alteração" do PDF é marcador de seção, não texto de evento."""
    from pathlib import Path

    import modules.compilador.application.folha_extraction as fx
    from modules.compilador.application.folha_extraction import extract_events_from_bi_pdf
    from modules.compilador.application.folha_models import CompilerOptions

    texto = "\n".join(
        [
            "MARÇO:",
            "APRESENTACAO – POR TÉRMINO DE FÉRIAS",
            "- a 26, BI Nº 24 :",
            "Apresentou-se em 23 MAR 26, pronto para o serviço.",
            "ABRIL: Sem Alteração",
            "MAIO: Sem Alteração",
            "JUNHO: Sem Alteração",
        ]
    )
    original = fx.extract_pdf_text
    fx.extract_pdf_text = lambda _p: texto
    try:
        events = extract_events_from_bi_pdf(Path("/x.pdf"), CompilerOptions(ano=2026, semestre="1"))
    finally:
        fx.extract_pdf_text = original

    assert len(events) == 1
    assert "Sem Alteração" not in events[0].corpo
    assert "ABRIL" not in events[0].corpo
