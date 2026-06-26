from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata


@dataclass(slots=True)
class NormalizedQmResult:
    display: str
    raw: str
    status: str
    warnings: list[str] = field(default_factory=list)


KNOWN_QMS = [
    ("QUADRO ESPECIAL", "QUADRO ESPECIAL"),
    ("MATERIAL BELICO", "MATERIAL BÉLICO"),
    ("INTENDENCIA", "INTENDÊNCIA"),
    ("INFANTARIA", "INFANTARIA"),
    ("CAVALARIA", "CAVALARIA"),
    ("ARTILHARIA", "ARTILHARIA"),
    ("ENGENHARIA", "ENGENHARIA"),
    ("COMUNICACOES", "COMUNICAÇÕES"),
    ("SAUDE", "SAÚDE"),
    ("MUSICO", "MÚSICO"),
    ("ADMINISTRACAO GERAL", "ADMINISTRAÇÃO GERAL"),
]


def normalize_qas_qms_qm_for_header(raw: str | None) -> NormalizedQmResult:
    original = normalize_space(raw or "")
    comparable = normalize_ascii(original).upper()
    comparable = re.sub(r"\b\d{3,6}\s*-\s*", "", comparable)
    comparable = re.sub(r"\b(?:QAS/QMS/QM|QAS QMS QM|QMS|QMG|QM)\s*-?\s*", "", comparable)
    comparable = normalize_space(comparable.replace(" 00-", " "))

    if not comparable:
        return NormalizedQmResult(display="", raw=original, status="PENDING", warnings=["QMS_QM_NAO_RECONHECIDO"])

    if any(token in comparable for token in ("QUALQUER QMG", "QUALQUER QMP", "QUALQUER", "QMG 00")):
        return NormalizedQmResult(display="", raw=original, status="GENERIC_EMPTY", warnings=["QMS_QM_GENERICO"])

    for marker, display in KNOWN_QMS:
        if marker in comparable:
            status = "OK" if comparable == marker else "NORMALIZED"
            return NormalizedQmResult(display=display, raw=original, status=status, warnings=[])

    return NormalizedQmResult(display="", raw=original, status="PENDING", warnings=["QMS_QM_NAO_RECONHECIDO"])


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_ascii(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char))
