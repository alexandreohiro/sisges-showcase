from __future__ import annotations

from dataclasses import dataclass
import re


EVENTO_DIRETO = "EVENTO_DIRETO"
EVENTO_INDIRETO = "EVENTO_INDIRETO"
EVENTO_TERCEIROS = "EVENTO_TERCEIROS"
EVENTO_BENEFICIARIO = "EVENTO_BENEFICIARIO"
EVENTO_PAGAMENTO = "EVENTO_PAGAMENTO"
EVENTO_SAUDE = "EVENTO_SAUDE"
EVENTO_SINDICANCIA = "EVENTO_SINDICANCIA"
EVENTO_TAF = "EVENTO_TAF"
EVENTO_FERIAS = "EVENTO_FERIAS"
EVENTO_INSTRUCAO = "EVENTO_INSTRUCAO"
EVENTO_PROMOCAO = "EVENTO_PROMOCAO"
EVENTO_CURSO = "EVENTO_CURSO"

FILTERABLE_CATEGORIES = {
    EVENTO_BENEFICIARIO,
    EVENTO_PAGAMENTO,
    EVENTO_TERCEIROS,
}

KEEP_CATEGORIES = {
    EVENTO_TAF,
    EVENTO_FERIAS,
    EVENTO_SINDICANCIA,
    EVENTO_SAUDE,
    EVENTO_INSTRUCAO,
    EVENTO_PROMOCAO,
    EVENTO_CURSO,
}

DEFAULT_POLICY_CODE = "OM_PRIVACY_FILTER_V1"
COMPILADOR_PARTE1_FILTER_POLICY_ENABLED = False


@dataclass(slots=True)
class EventFilterPolicyConfig:
    enable_event_filter_policy: bool = COMPILADOR_PARTE1_FILTER_POLICY_ENABLED
    policy_code: str = DEFAULT_POLICY_CODE


@dataclass(slots=True)
class EventFilterDecision:
    category: str
    should_filter: bool
    reason: str = ""
    policy_code: str = DEFAULT_POLICY_CODE

    @property
    def policy(self) -> str:
        return self.policy_code

    def to_filtered_event(self, *, titulo: str, source_bi: str = "") -> dict:
        if self.should_filter and not self.reason:
            raise ValueError("Evento filtrado exige reason.")
        return {
            "titulo": titulo,
            "reason": self.reason,
            "source_bi": source_bi,
            "policy": self.policy_code,
            "policy_code": self.policy_code,
            "category": self.category,
        }


def classify_event(titulo: str, corpo: str = "") -> str:
    text = _normalize(f"{titulo} {corpo}")
    if "DECLARACAO DE BENEFICIARIO" in text or "BENEFICIARIO" in text:
        return EVENTO_BENEFICIARIO
    if any(token in text for token in ("PAGAMENTO", "AUXILIO", "INDENIZACAO", "SALARIO")):
        return EVENTO_PAGAMENTO
    if any(token in text for token in ("TERCEIRO", "DEPENDENTE", "PENSIONISTA")):
        return EVENTO_TERCEIROS
    if "TESTE DE AVALIACAO FISICA" in text or re.search(r"\bTAF\b", text):
        return EVENTO_TAF
    if "FERIAS" in text:
        return EVENTO_FERIAS
    if "SINDICANCIA" in text:
        return EVENTO_SINDICANCIA
    if any(token in text for token in ("CONVALESCENCA", "SAUDE", "MEDIC")):
        return EVENTO_SAUDE
    if "PROMOCAO" in text:
        return EVENTO_PROMOCAO
    if "CURSO" in text:
        return EVENTO_CURSO
    if "INSTRUCAO" in text:
        return EVENTO_INSTRUCAO
    return EVENTO_DIRETO


def decide_event_filter(titulo: str, corpo: str = "", *, policy: str = DEFAULT_POLICY_CODE) -> EventFilterDecision:
    category = classify_event(titulo, corpo)
    if category in FILTERABLE_CATEGORIES:
        suffix = {
            EVENTO_BENEFICIARIO: "EVENTO_BENEFICIARIO_PRIVACIDADE",
            EVENTO_PAGAMENTO: "EVENTO_PAGAMENTO_PRIVACIDADE",
            EVENTO_TERCEIROS: "EVENTO_TERCEIROS_PRIVACIDADE",
        }[category]
        return EventFilterDecision(category=category, should_filter=True, reason=suffix, policy_code=policy)
    return EventFilterDecision(category=category, should_filter=False, policy_code=policy)


def apply_event_filter_policy(
    events: list[dict],
    *,
    config: EventFilterPolicyConfig | None = None,
) -> tuple[list[dict], list[dict]]:
    """Aplica a politica somente quando explicitamente habilitada.

    Por padrao o SISGES apenas classifica eventos filtraveis. A remocao da
    1a Parte exige decisao operacional rastreada em filtered_events.
    """
    config = config or EventFilterPolicyConfig()
    if not config.enable_event_filter_policy:
        return events, []

    kept: list[dict] = []
    filtered: list[dict] = []
    for event in events:
        title = str(event.get("titulo") or event.get("title") or "")
        body = str(event.get("corpo") or event.get("body") or "")
        source_bi = str(event.get("referencia_bi") or event.get("source_bi") or "")
        decision = decide_event_filter(title, body, policy=config.policy_code)
        if decision.should_filter:
            filtered.append(decision.to_filtered_event(titulo=title, source_bi=source_bi))
        else:
            kept.append(event)
    return kept, filtered


def _normalize(value: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).upper()
