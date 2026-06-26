from modules.compilador.domain.entities import CompilationRecord
from shared.utils.strings import normalize_line_breaks
from xml.sax.saxutils import escape


def _clean_text(value: str) -> str:
    return normalize_line_breaks((value or "").strip())


def split_body_into_paragraphs(text: str) -> list[str]:
    text = _clean_text(text)
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    return paragraphs if paragraphs else [text]


def build_part1_blocks(record: CompilationRecord) -> list[dict[str, str]]:
    if not record.part1:
        return []

    blocks: list[dict[str, str]] = []
    current_month = None

    for item in record.part1:
        if item.mes != current_month:
            current_month = item.mes
            blocks.append({"type": "month", "text": f"{item.mes}:"})
            blocks.append({"type": "blank", "text": ""})

        if item.titulo:
            blocks.append({"type": "title", "text": _clean_text(item.titulo)})

        if item.referencia:
            blocks.append({"type": "reference", "text": _clean_text(item.referencia)})

        if item.corpo:
            for paragraph in split_body_into_paragraphs(item.corpo):
                blocks.append({"type": "body", "text": paragraph})

        blocks.append({"type": "blank", "text": ""})

    return blocks


def build_part1_text(record: CompilationRecord) -> str:
    blocks = build_part1_blocks(record)
    if not blocks:
        return ""

    return "\n".join(block["text"] for block in blocks)


def build_nome_formatado_xml(
    nome_completo: str,
    nome_guerra: str,
    bold_style_name: str,
) -> str:
    nome_completo = (nome_completo or "").strip()
    nome_guerra = (nome_guerra or "").strip()

    if not nome_completo:
        return ""

    if not nome_guerra:
        return escape(nome_completo)

    upper_nome = nome_completo.upper()
    upper_guerra = nome_guerra.upper()

    start = upper_nome.find(upper_guerra)
    if start < 0:
        return escape(nome_completo)

    end = start + len(nome_guerra)

    before = escape(nome_completo[:start])
    middle = escape(nome_completo[start:end])
    after = escape(nome_completo[end:])

    return (
        f'{before}<text:span text:style-name="{bold_style_name}">{middle}</text:span>{after}'
    )


def build_placeholder_map(record: CompilationRecord) -> dict[str, str]:
    return {
        "[NOME]": record.header.nome_completo or "",
        "[NOME_GUERRA]": record.header.nome_guerra or "",
        "[GRADUACAO]": record.header.graduacao or "",
        "[QM]": record.header.qm or "",
        "[IDENTIDADE]": record.header.identidade or "",
        "[PERIODO]": record.header.periodo or "",
        "[DATA_DE_PRACA]": record.header.data_de_praca or "",
        "[TC]": record.part2.tc or "",
        "[TC_ARREG]": record.part2.tc_arreg or "",
        "[TC_NAO_ARREG]": record.part2.tc_nao_arreg or "",
        "[TC_TRANSITO]": record.part2.tc_transito or "",
        "[TC_INSTALACAO]": record.part2.tc_instalacao or "",
        "[TNC]": record.part2.tnc or "",
        "[TSCMM]": record.part2.tscmm or "",
        "[TSSD]": record.part2.tssd or "",
        "[TSNR]": record.part2.tsnr or "",
        "[TTES]": record.part2.ttes or "",
    }