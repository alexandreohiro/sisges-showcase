import re
from modules.compilador.domain.entities import CompilationRecord, Part1Entry, Part2Times
from modules.compilador.domain.header_parser import parse_header
from modules.validacao.domain.part1_semantic_cleaner import (
    is_invalid_part1_title,
    clean_part1_body_start,
)

MONTHS = [
    "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO",
    "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"
]

MONTH_PATTERN = r"^(JANEIRO|FEVEREIRO|MARÇO|ABRIL|MAIO|JUNHO|JULHO|AGOSTO|SETEMBRO|OUTUBRO|NOVEMBRO|DEZEMBRO):\s*$"


def _normalize_spaces(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_part1_part2(text: str) -> tuple[str, str]:
    match = re.search(r"\b2ª PARTE\b", text, flags=re.IGNORECASE)
    if not match:
        return text, ""
    return text[:match.start()].strip(), text[match.start():].strip()


def _extract_part1_entries(part1_text: str) -> list[Part1Entry]:
    entries: list[Part1Entry] = []
    lines = [line.rstrip() for line in part1_text.splitlines()]

    current_month = ""
    current_title = ""
    current_ref = ""
    current_body: list[str] = []

    def flush():
        nonlocal current_title, current_ref, current_body, current_month
    
        if current_month and current_title:
            cleaned_body = "\n".join(s.strip() for s in current_body if s.strip())
            cleaned_body, body_diagnostics = clean_part1_body_start(cleaned_body)
    
            if not is_invalid_part1_title(current_title):
                body = _normalize_spaces(cleaned_body)
                entries.append(
                    Part1Entry(
                        mes=current_month,
                        titulo=_normalize_spaces(current_title),
                        referencia=_normalize_spaces(current_ref),
                        corpo=body,
                    )
                )
    
        current_title = ""
        current_ref = ""
        current_body = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        month_match = re.match(MONTH_PATTERN, line, flags=re.IGNORECASE)
        if month_match:
            flush()
            current_month = month_match.group(1).upper()
            i += 1
            continue

        # novo título: linha não vazia, fora da referência, e não é lixo de cabeçalho
        if current_month and not line.startswith("- a "):
            if is_invalid_part1_title(line):
                i += 1
                continue
            # se já havia um título e achamos outro, flush do item anterior
            if current_title and current_ref:
                flush()

            # este é o título
            current_title = line
            i += 1

            # próxima linha deve ser a referência
            if i < len(lines):
                next_line = lines[i].strip()
                if next_line.startswith("- a "):
                    current_ref = next_line
                    i += 1

                    # corpo até:
                    # - próximo mês
                    # - próxima linha que pareça título seguida de "- a "
                    while i < len(lines):
                        probe = lines[i].strip()

                        if not probe:
                            i += 1
                            continue

                        if re.match(MONTH_PATTERN, probe, flags=re.IGNORECASE):
                            break

                        # detectar início de próximo item
                        if (
                            i + 1 < len(lines)
                            and probe
                            and not probe.startswith("- a ")
                            and lines[i + 1].strip().startswith("- a ")
                        ):
                            break

                        if not is_invalid_part1_title(probe):
                            current_body.append(probe)
                        i += 1
                    continue

        i += 1

    flush()
    return entries


def _extract_time(patterns: list[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            value = match.group(1).strip()
            value = re.sub(r"\s+", "", value)
            value = (
                value.replace("anos", "a")
                .replace("meses", "m")
                .replace("dias", "d")
                .replace("ano", "a")
                .replace("mes", "m")
                .replace("dia", "d")
            )
            return value
    return ""


def _extract_part2(part2_text: str) -> Part2Times:
    p2 = Part2Times()

    # 1. TC
    p2.tc = _extract_time(
        [
            r"1\.\s*TEMPO COMPUTADO DE EFETIVO SERVIÇO\s*\(TC\).*?(\d+\s*a\s*\d+\s*m\s*\d+\s*d)",
            r"1\.\s*TEMPO COMPUTADO DE EFETIVO SERVIÇO\s*\(TC\).*?(\d+a\d+m\d+d)",
        ],
        part2_text,
    )

    # subitens do TC
    p2.tc_arreg = _extract_time(
        [
            r"[aA][\)\.\-:]?\s*Arregimentado.*?(\d+\s*a\s*\d+\s*m\s*\d+\s*d)",
            r"[aA][\)\.\-:]?\s*Arregimentado.*?(\d+a\d+m\d+d)",
        ],
        part2_text,
    )

    p2.tc_nao_arreg = _extract_time(
        [
            r"[bB][\)\.\-:]?\s*Não\s*Arregimentado.*?(\d+\s*a\s*\d+\s*m\s*\d+\s*d)",
            r"[bB][\)\.\-:]?\s*Não\s*Arregimentado.*?(\d+a\d+m\d+d)",
            r"[bB][\)\.\-:]?\s*N[aã]o\s*arregimentado.*?(\d+\s*a\s*\d+\s*m\s*\d+\s*d)",
        ],
        part2_text,
    )

    p2.tc_transito = _extract_time(
        [
            r"[cC][\)\.\-:]?\s*Tr[aâ]nsito.*?(\d+\s*a\s*\d+\s*m\s*\d+\s*d)",
            r"[cC][\)\.\-:]?\s*Tr[aâ]nsito.*?(\d+a\d+m\d+d)",
        ],
        part2_text,
    )

    p2.tc_instalacao = _extract_time(
        [
            r"[dD][\)\.\-:]?\s*Instala[cç][aã]o.*?(\d+\s*a\s*\d+\s*m\s*\d+\s*d)",
            r"[dD][\)\.\-:]?\s*Instala[cç][aã]o.*?(\d+a\d+m\d+d)",
        ],
        part2_text,
    )

    # 2. TNC
    p2.tnc = _extract_time(
        [
            r"2\.\s*TEMPO N[ÃA]O COMPUTADO\s*\(TNC\).*?(\d+\s*a\s*\d+\s*m\s*\d+\s*d)",
            r"2\.\s*TEMPO N[ÃA]O COMPUTADO\s*\(TNC\).*?(\d+a\d+m\d+d)",
        ],
        part2_text,
    )

    # 3. TSCMM
    p2.tscmm = _extract_time(
        [
            r"3\.\s*TEMPO DE SERVIÇO COMPUT[ÁA]VEL PARA MEDALHA MILITAR.*?(\d+\s*a\s*\d+\s*m\s*\d+\s*d)",
            r"3\.\s*TEMPO DE SERVIÇO COMPUT[ÁA]VEL PARA MEDALHA MILITAR.*?(\d+a\d+m\d+d)",
        ],
        part2_text,
    )

    # 4. TSSD — aceitar nomes alternativos
    p2.tssd = _extract_time(
        [
            r"(?:4\.\s*)?TEMPO DE SERVIÇO EM SITUAÇÕES DIVERSAS\s*\(TSSD\).*?(\d+\s*a\s*\d+\s*m\s*\d+\s*d)",
            r"(?:4\.\s*)?TEMPO DE SERVIÇO EM SITUAÇÕES DIVERSAS\s*\(TSSD\).*?(\d+a\d+m\d+d)",
            r"(?:4\.\s*)?TSSD.*?(\d+\s*a\s*\d+\s*m\s*\d+\s*d)",
            r"(?:4\.\s*)?TSSD.*?(\d+a\d+m\d+d)",
        ],
        part2_text,
    )

    # 5. TSNR
    p2.tsnr = _extract_time(
        [
            r"(?:5\.\s*)?TEMPO DE SERVIÇO NACIONAL RELEVANTE\s*\(TSNR\).*?(\d+\s*a\s*\d+\s*m\s*\d+\s*d)",
            r"(?:5\.\s*)?TEMPO DE SERVIÇO NACIONAL RELEVANTE\s*\(TSNR\).*?(\d+a\d+m\d+d)",
            r"(?:5\.\s*)?TSNR.*?(\d+\s*a\s*\d+\s*m\s*\d+\s*d)",
            r"(?:5\.\s*)?TSNR.*?(\d+a\d+m\d+d)",
        ],
        part2_text,
    )

    # 6. TTES
    p2.ttes = _extract_time(
        [
            r"(?:6\.\s*)?TEMPO TOTAL DE EFETIVO SERVIÇO\s*\(TTES\).*?(\d+\s*a\s*\d+\s*m\s*\d+\s*d)",
            r"(?:6\.\s*)?TEMPO TOTAL DE EFETIVO SERVIÇO\s*\(TTES\).*?(\d+a\d+m\d+d)",
            r"(?:6\.\s*)?TTES.*?(\d+\s*a\s*\d+\s*m\s*\d+\s*d)",
            r"(?:6\.\s*)?TTES.*?(\d+a\d+m\d+d)",
        ],
        part2_text,
    )

    if any([p2.tc, p2.tscmm, p2.ttes, p2.tssd, p2.tsnr]):
        p2.origem = "extraido"

    return p2

def parse_record(text: str) -> CompilationRecord:
    record = CompilationRecord()
    record.raw_text = text
    record.header = parse_header(text)

    part1_text, part2_text = _split_part1_part2(text)
    record.part1 = _extract_part1_entries(part1_text)
    record.part2 = _extract_part2(part2_text)

    return record