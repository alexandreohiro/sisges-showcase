import pytest

from modules.compilador.application.event_filter_policy import (
    EVENTO_BENEFICIARIO,
    EVENTO_FERIAS,
    EVENTO_PAGAMENTO,
    EVENTO_SINDICANCIA,
    EVENTO_TAF,
    EventFilterPolicyConfig,
    apply_event_filter_policy,
    classify_event,
    decide_event_filter,
)


def test_declaracao_beneficiario_classifica_e_filtra():
    decision = decide_event_filter("DECLARACAO DE BENEFICIARIO - Atualizacao")

    assert decision.category == EVENTO_BENEFICIARIO
    assert decision.should_filter is True
    assert decision.reason == "EVENTO_BENEFICIARIO_PRIVACIDADE"


def test_evento_pagamento_classifica_e_filtra():
    decision = decide_event_filter("PAGAMENTO PESSOAL - Atualizacao")

    assert decision.category == EVENTO_PAGAMENTO
    assert decision.should_filter is True


def test_taf_permanece():
    decision = decide_event_filter("TESTE DE AVALIACAO FISICA - Resultado")

    assert decision.category == EVENTO_TAF
    assert decision.should_filter is False


def test_ferias_permanece():
    assert decide_event_filter("FERIAS - Concessao").category == EVENTO_FERIAS
    assert decide_event_filter("FERIAS - Concessao").should_filter is False


def test_sindicancia_permanece():
    assert classify_event("SINDICANCIA - Solucao") == EVENTO_SINDICANCIA
    assert decide_event_filter("SINDICANCIA - Solucao").should_filter is False


def test_evento_filtrado_exige_reason():
    decision = decide_event_filter("DECLARACAO DE BENEFICIARIO - Atualizacao")
    filtered = decision.to_filtered_event(titulo="DECLARACAO DE BENEFICIARIO")
    assert filtered["reason"]
    assert filtered["policy_code"] == "OM_PRIVACY_FILTER_V1"

    decision.reason = ""
    with pytest.raises(ValueError):
        decision.to_filtered_event(titulo="DECLARACAO DE BENEFICIARIO")


def test_filter_policy_does_not_remove_events_by_default():
    events = [
        {
            "titulo": "DECLARACAO DE BENEFICIARIO - Atualizacao",
            "corpo": "Dados indiretos de beneficiario.",
            "referencia_bi": "BI No 84",
        }
    ]

    kept, filtered = apply_event_filter_policy(events)

    assert kept == events
    assert filtered == []


def test_filter_policy_requires_explicit_enablement_to_remove_event():
    events = [
        {
            "titulo": "DECLARACAO DE BENEFICIARIO - Atualizacao",
            "corpo": "Dados indiretos de beneficiario.",
            "referencia_bi": "BI No 84",
        }
    ]

    kept, filtered = apply_event_filter_policy(
        events,
        config=EventFilterPolicyConfig(enable_event_filter_policy=True, policy_code="OM_PRIVACY_FILTER_V1"),
    )

    assert kept == []
    assert filtered[0]["reason"] == "EVENTO_BENEFICIARIO_PRIVACIDADE"
    assert filtered[0]["policy_code"] == "OM_PRIVACY_FILTER_V1"
