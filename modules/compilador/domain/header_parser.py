import re
from modules.compilador.domain.entities import HeaderData


def _extract_first(patterns: list[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip()
    return ""


def _extract_periodo(text: str) -> str:
    patterns = [
        # prioridade máxima: período com duas datas
        r"CP:\s*PERÍODO:\s*(\d{2}/\d{2}/\d{4}\s*a\s*\d{2}/\d{2}/\d{4})",
        r"PERÍODO:\s*(\d{2}/\d{2}/\d{4}\s*a\s*\d{2}/\d{2}/\d{4})",
        # fallback só se não houver intervalo
        r"^PERÍODO:\s*([^\n]+?)\s*$",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            value = match.group(1).strip()

            # se capturou só ano, ignora como período canônico
            if re.fullmatch(r"\d{4}", value):
                continue

            return value

    return ""


def _clean_identity(value: str) -> str:
    if not value:
        return ""

    value = re.split(r"\s+\d+º\s+Semestre", value, maxsplit=1, flags=re.IGNORECASE)[0]
    value = re.split(r"\s+CP:", value, maxsplit=1, flags=re.IGNORECASE)[0]
    value = value.strip()

    match = re.search(r"\d{3,}[-/]\d+|\d{7,}-\d+|\d{7,}", value)
    if match:
        return match.group(0).strip()

    return value


def parse_header(text: str) -> HeaderData:
    header = HeaderData()

    header.nome_completo = _extract_first(
        [
            r"^NOME:\s*(.+?)\s*$",
        ],
        text,
    )

    header.graduacao = _extract_first(
        [
            r"^GRADUAÇÃO:\s*(.+?)\s*$",
            r"^POSTO/GRADUAÇÃO:\s*(.+?)\s*$",
        ],
        text,
    )

    header.qm = _extract_first(
        [
            r"^ARMA/QUADRO/SERVIÇO:\s*(.+?)\s*$",
            r"^ARMA/QUARO/SERVIÇO:\s*(.+?)\s*$",
            r"^QAS/QMS:\s*(.+?)\s*$",
            r"^QM:\s*(.+?)\s*$",
        ],
        text,
    )

    identidade_bruta = _extract_first(
        [
            r"^IDENTIDADE:\s*(.+?)\s*$",
            r"^Idt:\s*(.+?)\s*$",
            r"^IDT:\s*(.+?)\s*$",
        ],
        text,
    )
    header.identidade = _clean_identity(identidade_bruta)

    header.periodo = _extract_periodo(text)

    return header