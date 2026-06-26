from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date
from pathlib import Path
import re
import unicodedata
from typing import Any

import pdfplumber

from modules.gestao_pessoal.importadores.sicapex.schemas import (
    SicapexAfastamento,
    SicapexComportamento,
    SicapexDataPraca,
    SicapexMovimentacao,
    SicapexParsedRecord,
    SicapexPeriodoServicoSugerido,
    SicapexSituacaoRegulamentar,
    SicapexTempoServico,
)
from shared.utils.qms import normalize_qas_qms_qm_for_header
from shared.utils.hashing import sha256_file


SECTION_TITLES = {
    "DADOS PESSOAIS",
    "DADOS FUNCIONAIS",
    "DATAS DE PRACA",
    "AFASTAMENTOS",
    "AGREGACOES",
    "ALTERACOES",
    "HABILITACOES",
    "INSPECOES DE SAUDE",
    "JUSTICA E DISCIPLINA",
    "MOVIMENTACOES",
    "SITUACOES REGULAMENTARES",
    "TEMPO DE SERVICO",
    "TESTES DE APTIDAO",
    "TAF",
    "TAT",
}

SENSITIVE_KEYS = {
    "cpf",
    "endereco",
    "email",
    "banco",
    "banc",
    "agencia",
    "conta",
    "filiacao",
    "nome_pai",
    "nome_mae",
    "saude",
    "medico",
}


def parse_sicapex_pdf(pdf_path: Path) -> SicapexParsedRecord:
    path = Path(pdf_path)
    text = extract_pdf_text(path)
    record = parse_sicapex_text(text)
    record.source_filename = path.name
    record.source_sha256 = sha256_file(path)
    return record


def extract_pdf_text(path: Path) -> str:
    parts: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def parse_sicapex_text(raw_text: str) -> SicapexParsedRecord:
    text = clean_text(raw_text)
    record = SicapexParsedRecord(raw_excerpt=text[:1500])
    if not text.strip():
        record.ocr_required = True
        record.pending.append("OCR_REQUIRED")
        return record

    sections = group_sections(text.splitlines())
    record.nome_completo = capture(text, r"Nome:\s*([^\n]+)") or ""
    record.sexo = capture(text, r"Sexo:\s*(Masculino|Feminino|MASCULINO|FEMININO)") or ""
    record.estado_civil = capture(
        text,
        r"Estado Civil:\s*(Casado|Solteiro|Divorciado|Viuvo|Vi[uú]vo|CASADO|SOLTEIRO|DIVORCIADO)",
    ) or ""
    record.identidade_militar = capture(text, r"\bIdt\s+([0-9A-Za-z.\-]+)\s+Prec-CP:") or ""
    record.prec_cp = capture(text, r"Prec-CP:\s*([0-9A-Za-z.\-]+)") or ""
    record.situacao_militar = capture(text, r"Situacao\s+(Carreira/Ativo|Reserva|Reforma|Inativo)") or ""
    record.situacao_servico = capture(text, r"Situacao\s+(Efetivo pronto|Adido[^\n]*|Nao Apresentado[^\n]*)") or ""

    parse_functional_line(record, text)
    parse_qm(record, text)
    parse_current_om(record, text)
    parse_data_praca(record, sections.get("DATAS DE PRACA", []))
    validate_data_praca(record, text)
    parse_service_time_fields(record, text)

    record.afastamentos = parse_afastamentos(sections.get("AFASTAMENTOS", []))
    record.agregacoes = parse_raw_rows(sections.get("AGREGACOES", []))
    record.alteracoes_arquivadas = parse_raw_rows(sections.get("ALTERACOES", []))
    record.habilitacoes = parse_raw_rows(sections.get("HABILITACOES", []))
    record.inspecoes_saude = parse_raw_rows(sections.get("INSPECOES DE SAUDE", []))
    record.historico_comportamento = parse_comportamentos(sections.get("JUSTICA E DISCIPLINA", []))
    record.comportamento_atual = latest_comportamento(record.historico_comportamento)
    record.movimentacoes = parse_movimentacoes(sections.get("MOVIMENTACOES", []))
    record.situacoes_regulamentares = parse_situacoes_regulamentares(
        sections.get("SITUACOES REGULAMENTARES", [])
    )
    record.desconto_tempo_servico = parse_tempo_servico(sections.get("DESCONTOS TEMPO SERVICO", []))
    record.acrescimos_tempo_servico = parse_tempo_servico(
        sections.get("ACRESCIMOS TEMPO SERVICO", [])
    )
    record.tempo_efetivo_servico_apos_ultima = parse_tempo_efetivo(text)
    record.tempo_efetivo_servico_apos_ultima_dias = parse_int(record.tempo_efetivo_servico_apos_ultima)
    record.tempo_servico_bruto_json = build_tempo_servico_bruto(record)
    record.periodos_servico_sugeridos = build_periodos_servico_sugeridos(record)
    record.pendencias_calculo = build_pendencias_calculo(record)
    record.observacoes_calculo = build_observacoes_calculo(record)
    record.taf = parse_raw_rows(sections.get("TAF", []) + sections.get("TESTES DE APTIDAO", []))
    record.tat = parse_raw_rows(sections.get("TAT", []))

    if not record.nome_completo:
        record.pending.append("NOME_COMPLETO_PENDENTE")
    if not record.nome_guerra and record.nome_completo:
        record.nome_guerra = record.nome_completo.split()[-1]
        record.pending.append("NOME_GUERRA_FALLBACK")
    if not record.identidade_militar:
        record.pending.append("IDENTIDADE_MILITAR_PENDENTE")
    if not record.qas_qms_qm:
        record.pending.append("QMS_QM_PENDENTE")
    return record


def clean_text(raw_text: str) -> str:
    lines: list[str] = []
    for raw in raw_text.splitlines():
        line = normalize_space(raw)
        if not line:
            continue
        if re.match(r"^Pagina\s+\d+\s+de\s+\d+", strip_accents(line), flags=re.I):
            continue
        if re.match(r"^Idt\s+[0-9.\-]+$", line, flags=re.I):
            continue
        if "INFORMACAO PESSOAL" in strip_accents(line).upper():
            continue
        lines.append(line)
    return "\n".join(lines)


def group_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"CABECALHO": []}
    current = "CABECALHO"
    aliases = {
        "DATAS DE PRACA": "DATAS DE PRACA",
        "DATAS DE PRAA": "DATAS DE PRACA",
        "AGREGACOES": "AGREGACOES",
        "AGREGAES": "AGREGACOES",
        "ALTERACOES": "ALTERACOES",
        "ALTERAES": "ALTERACOES",
        "HABILITACOES": "HABILITACOES",
        "HABILITAES": "HABILITACOES",
        "INSPECOES DE SAUDE": "INSPECOES DE SAUDE",
        "INSPEES DE SAUDE": "INSPECOES DE SAUDE",
        "JUSTICA E DISCIPLINA": "JUSTICA E DISCIPLINA",
        "JUSTIA E DISCIPLINA": "JUSTICA E DISCIPLINA",
        "MOVIMENTACOES": "MOVIMENTACOES",
        "MOVIMENTAES": "MOVIMENTACOES",
        "SITUACOES REGULAMENTARES": "SITUACOES REGULAMENTARES",
        "SITUAES REGULAMENTARES": "SITUACOES REGULAMENTARES",
        "TEMPO DE SERVICO": "TEMPO DE SERVICO",
        "TEMPO DE SERVIO": "TEMPO DE SERVICO",
        "DESCONTO DE TEMPOS DE SERVICOS": "DESCONTOS TEMPO SERVICO",
        "ACRESCIMOS DE TEMPO DE SERVICO": "ACRESCIMOS TEMPO SERVICO",
        "TESTES DE APTIDAO": "TESTES DE APTIDAO",
    }
    for line in lines:
        raw_key = strip_accents(line).upper()
        key = re.sub(r"[^A-Z0-9]+", " ", raw_key).strip()
        alpha_key = re.sub(r"[^A-Z]+", " ", raw_key).strip()
        compact_alpha_key = re.sub(r"[^A-Z]+", "", raw_key)
        section = resolve_section_title((key, alpha_key, compact_alpha_key), aliases)
        if section:
            current = section
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return sections


def resolve_section_title(candidates: tuple[str, ...], aliases: dict[str, str]) -> str | None:
    compact_aliases = {re.sub(r"[^A-Z]+", "", alias): canonical for alias, canonical in aliases.items()}
    for candidate in candidates:
        section = aliases.get(candidate) or (candidate if candidate in SECTION_TITLES else None)
        if section:
            return section
        compact_section = compact_aliases.get(candidate)
        if compact_section:
            return compact_section
        for alias, canonical in aliases.items():
            if candidate.startswith(f"{alias} "):
                return canonical
        for alias, canonical in compact_aliases.items():
            if candidate.startswith(alias) and len(candidate) <= len(alias) + 4:
                return canonical
    return None


def parse_functional_line(record: SicapexParsedRecord, text: str) -> None:
    direct = capture(text, r"Posto/Grad:\s*([^\n]+?)\s+Nome\s+")
    if direct:
        record.posto_grad_abrev = direct
        record.posto_grad_extenso = expand_posto_grad(direct)
    named = re.search(
        r"Posto/Grad:\s*(?P<posto>.+?)\s+Nome\s+(?P<guerra>.+?)\s+Dt\s+Turma:\s*\d{2}/\d{2}/\d{4}",
        text,
        flags=re.I,
    )
    if named:
        record.posto_grad_abrev = normalize_space(named.group("posto"))
        record.posto_grad_extenso = expand_posto_grad(record.posto_grad_abrev)
        nome_guerra = normalize_space(named.group("guerra"))
        if is_invalid_nome_guerra(nome_guerra):
            record.pending.append("NOME_GUERRA_INVALIDO")
        else:
            record.nome_guerra = nome_guerra
        return
    match = re.search(
        r"\b(?P<posto>(?:[123]o|[123]º)\s*Sgt|S\s*Ten|Cb|Sd|Cap|Maj|Cel|(?:[12]o|[12]º)\s*Ten)\s+"
        r"(?P<guerra>.+?)\s+(?P<data>\d{2}/\d{2}/\d{4})",
        text,
        flags=re.I,
    )
    if match:
        record.posto_grad_abrev = normalize_space(match.group("posto"))
        record.posto_grad_extenso = expand_posto_grad(record.posto_grad_abrev)
        nome_guerra = normalize_space(match.group("guerra"))
        if is_invalid_nome_guerra(nome_guerra):
            record.pending.append("NOME_GUERRA_INVALIDO")
        else:
            record.nome_guerra = nome_guerra


def parse_qm(record: SicapexParsedRecord, text: str) -> None:
    value = capture(text, r"(?:QAS/QMS/QM|QAS QMS QM)\s+([^\n]+)") or ""
    if not value:
        match = re.search(r"\b\d{3,6}\s*-\s*(?:QMS|QMG|QM)\s*-\s*[^\n]+", text, flags=re.I)
        value = normalize_space(match.group(0)) if match else ""
    result = normalize_qas_qms_qm_for_header(value)
    record.qas_qms_qm = result.display
    for warning in result.warnings:
        if warning not in record.pending:
            record.pending.append(warning)


def parse_current_om(record: SicapexParsedRecord, text: str) -> None:
    match = re.search(r"OM/CODOM:\s*(?P<om>.+?)\s+-\s*(?P<codom>[0-9.]+)", text, flags=re.I)
    if match:
        record.om_atual_nome = normalize_om_name(match.group("om"))
        record.om_atual_codom = normalize_space(match.group("codom"))
    record.data_inicio_om = parse_labeled_date(text, ["DT INICIO"])


def parse_data_praca(record: SicapexParsedRecord, lines: list[str]) -> None:
    if not lines:
        record.pending.append("DATA_PRACA_SECTION_NOT_FOUND")
        return

    for line in data_lines(lines):
        dates = re.findall(r"\d{2}/\d{2}/\d{4}", line)
        if not dates:
            continue

        data_praca = parse_br_date(dates[0])
        record.data_praca = data_praca
        remainder = normalize_space(line.split(dates[0], 1)[1])
        desligamento_match = re.match(r"^(?P<data>\d{2}/\d{2}/\d{4})\b", remainder)
        data_desligamento = parse_br_date(desligamento_match.group("data")) if desligamento_match else None
        remainder = re.sub(r"^(?:\d{2}/\d{2}/\d{4}|-)\s*", "", remainder)
        match = re.match(
            r"(?P<tipo>(?:Normal\s+)?(?:EB|Exercito|Marinha|Aeron[aã]utica)|Normal)\b\s*(?P<doc>.*)",
            remainder,
            flags=re.I,
        )
        if match:
            record.tipo_forca = normalize_space(match.group("tipo"))
            record.documento_praca = normalize_space(match.group("doc") or "")
        else:
            record.documento_praca = remainder
        record.datas_praca.append(
            SicapexDataPraca(
                data_praca=data_praca,
                data_desligamento=data_desligamento,
                tipo_forca=record.tipo_forca,
                documento=record.documento_praca,
                raw=line,
            )
        )
        return

    record.pending.append("DATA_PRACA_NOT_FOUND")
    return

def validate_data_praca(record: SicapexParsedRecord, text: str) -> None:
    if not record.data_praca:
        return
    if record.data_praca.year < 1950:
        record.pending.append("DATA_PRACA_INVALIDA")

    data_nascimento = parse_br_date(
        capture(text, r"(?:Data|Dt)\s+Nascimento:?\s*([0-9/]+)") or ""
    )
    if data_nascimento and data_nascimento == record.data_praca:
        record.pending.append("DATA_PRACA_EQUALS_DATA_NASCIMENTO")


def parse_afastamentos(lines: list[str]) -> list[SicapexAfastamento]:
    result: list[SicapexAfastamento] = []
    for line in data_lines(lines):
        dates = re.findall(r"\d{2}/\d{2}/\d{4}", line)
        if len(dates) < 2:
            result.append(SicapexAfastamento(raw=line))
            continue
        before = line.split(dates[0], 1)[0]
        quantity = re.search(r"(\d+)\s*$", before)
        modalidade = before[: quantity.start()].strip() if quantity else before
        result.append(
            SicapexAfastamento(
                modalidade=normalize_space(modalidade),
                quantidade_dias=int(quantity.group(1)) if quantity else None,
                data_inicio=parse_br_date(dates[0]),
                data_fim=parse_br_date(dates[1]),
                documento=normalize_space(line.split(dates[1], 1)[1]),
                raw=line,
            )
        )
    return result


def parse_movimentacoes(lines: list[str]) -> list[SicapexMovimentacao]:
    result: list[SicapexMovimentacao] = []
    for line in merge_wrapped_rows(lines):
        dates = re.findall(r"\d{2}/\d{2}/\d{4}", line)
        codom = capture(line, r"^(\d{2,6})\b") or ""
        result.append(
            SicapexMovimentacao(
                codom=codom,
                om=normalize_space(re.sub(r"^\d{2,6}\s*", "", line.split(dates[0], 1)[0])) if dates else "",
                data_inicio=parse_br_date(dates[0]) if dates else None,
                data_fim=parse_br_date(dates[1]) if len(dates) > 1 else None,
                raw=line,
            )
        )
    return result


def parse_situacoes_regulamentares(lines: list[str]) -> list[SicapexSituacaoRegulamentar]:
    result: list[SicapexSituacaoRegulamentar] = []
    for line in merge_wrapped_rows(lines):
        dates = re.findall(r"\d{2}/\d{2}/\d{4}", line)
        result.append(
            SicapexSituacaoRegulamentar(
                codom=capture(line, r"^(\d{2,6})\b") or "",
                data_inicio=parse_br_date(dates[0]) if dates else None,
                data_fim=parse_br_date(dates[1]) if len(dates) > 1 else None,
                raw=line,
            )
        )
    return result


def parse_comportamentos(lines: list[str]) -> list[SicapexComportamento]:
    result: list[SicapexComportamento] = []
    for line in data_lines(lines):
        normalized = strip_accents(line).upper()
        match = re.search(r"\b(BOM|OTIMO|EXCEPCIONAL|INSUFICIENTE)\b", normalized)
        if not match:
            continue
        date_match = re.search(r"\d{2}/\d{2}/\d{4}", line)
        document = line.split(date_match.group(0), 1)[1] if date_match else ""
        result.append(
            SicapexComportamento(
                tipo=normalize_comportamento(match.group(1)),
                data=parse_br_date(date_match.group(0)) if date_match else None,
                documento=normalize_space(document),
                raw=line,
            )
        )
    return result


def latest_comportamento(items: list[SicapexComportamento]) -> SicapexComportamento | None:
    dated = [item for item in items if item.data]
    if dated:
        return sorted(dated, key=lambda item: item.data or date.min)[-1]
    return items[-1] if items else None


def parse_tempo_servico(lines: list[str]) -> list[SicapexTempoServico]:
    result: list[SicapexTempoServico] = []
    for line in data_lines(lines):
        if is_noise_tempo_servico_line(line):
            continue
        dates = re.findall(r"\d{2}/\d{2}/\d{4}", line)
        tempo = capture(line, r"(\d{1,3}\s*a\s*\d{1,2}\s*m\s*\d{1,2}\s*d|\d{1,3}a\d{1,2}m\d{1,2}d)") or ""
        dias = parse_tempo_dias(line)
        if not dates and not tempo and dias is None:
            continue
        documento = extract_document_after_tempo(line, tempo, dias)
        before_date = normalize_space(line.split(dates[0], 1)[0]) if dates else line
        result.append(
            SicapexTempoServico(
                tipo=normalize_space(before_date),
                subtipo=normalize_space(before_date),
                tempo=tempo,
                dias=dias,
                documento=documento,
                data_inicio=parse_br_date(dates[0]) if dates else None,
                data_fim=parse_br_date(dates[1]) if len(dates) > 1 else None,
                raw=line,
            )
        )
    return result


def is_noise_tempo_servico_line(line: str) -> bool:
    normalized = strip_accents(normalize_space(line)).upper()
    if not normalized:
        return True
    if normalized.startswith(("MOTIVO ", "TIPO DE SERVICO ", "DT INICIO ", "DATA ")):
        return True
    if "NENHUM REGISTRO ENCONTRADO" in normalized:
        return True
    return bool(re.fullmatch(r"[-.:\s0-9I]+", normalized))


def parse_tempo_efetivo(text: str) -> str:
    normalized = strip_accents(text)
    dias_match = re.search(
        r"Tempo\s+efetivo\s+servico\s+apos\s+a\s+ultima\s+([\d.]+)\s+dias",
        normalized,
        flags=re.I,
    )
    if dias_match:
        return dias_match.group(1).replace(".", "")
    return capture(text, r"Tempo Efetivo.*?(?:Ultima|Última).*?(\d{2}a\d{2}m\d{2}d)") or ""


def parse_tempo_dias(value: str) -> int | None:
    dias_match = re.search(r"([\d.]+)\s+dias?", strip_accents(value), flags=re.I)
    if dias_match:
        return parse_int(dias_match.group(1))
    admin = parse_admin_time(value)
    if admin:
        anos, meses, dias = admin
        return anos * 365 + meses * 30 + dias
    return None


def extract_document_after_tempo(line: str, tempo: str, dias: int | None) -> str:
    if tempo and tempo in line:
        return normalize_space(line.split(tempo, 1)[1])
    if dias is not None:
        match = re.search(r"[\d.]+\s+dias?\s*(?P<rest>.*)$", line, flags=re.I)
        if match:
            return normalize_space(match.group("rest"))
    return ""


def parse_service_time_fields(record: SicapexParsedRecord, text: str) -> None:
    record.apresentacao_gu = parse_labeled_date(
        text,
        ["APRESENTACAO NA GU", "APRESENTACAO GU"],
    )
    record.data_incorporacao = (
        parse_labeled_date(text, ["DATA DE INCORPORACAO", "DATA INCORPORACAO", "DT INCORPORACAO"])
        or record.data_praca
    )
    record.data_engajamento = parse_labeled_date(
        text,
        ["DATA DE ENGAJAMENTO", "DATA ENGAJAMENTO", "DT ENGAJAMENTO"],
    )
    record.data_reengajamento = parse_labeled_date(
        text,
        ["DATA DE REENGAJAMENTO", "DATA REENGAJAMENTO", "DT REENGAJAMENTO"],
    )
    record.data_desengajamento = parse_labeled_date(
        text,
        ["DATA DE DESENGAJAMENTO", "DATA DESENGAJAMENTO", "DT DESENGAJAMENTO"],
    )
    record.data_licenciamento = parse_labeled_date(
        text,
        ["DATA DE LICENCIAMENTO", "DATA LICENCIAMENTO", "DT LICENCIAMENTO"],
    )
    record.data_exclusao_servico_ativo = parse_labeled_date(
        text,
        [
            "EXCLUSAO DO SERVICO ATIVO",
            "DATA DE EXCLUSAO DO SERVICO ATIVO",
            "DT EXCLUSAO DO SERVICO ATIVO",
        ],
    )
    record.ultima_promocao = parse_labeled_date(
        text,
        ["ULTIMA PROMOCAO", "DT ULTIMA"],
    )

    anterior = parse_labeled_admin_time(text, ["TEMPO DE SERVICO ANTERIOR", "TEMPO SERVICO ANTERIOR"])
    if anterior:
        (
            record.tempo_servico_anterior_anos,
            record.tempo_servico_anterior_meses,
            record.tempo_servico_anterior_dias,
        ) = anterior

    publico = parse_labeled_admin_time(text, ["TEMPO DE SERVICO PUBLICO", "TEMPO SERVICO PUBLICO"])
    if publico:
        (
            record.tempo_servico_publico_anos,
            record.tempo_servico_publico_meses,
            record.tempo_servico_publico_dias,
        ) = publico


def parse_labeled_date(text: str, labels: list[str]) -> date | None:
    for line in text.splitlines():
        normalized = strip_accents(line).upper()
        if not any(label in normalized for label in labels):
            continue
        match = re.search(r"\d{2}/\d{2}/\d{4}", line)
        if match:
            return parse_br_date(match.group(0))
    return None


def parse_labeled_admin_time(text: str, labels: list[str]) -> tuple[int, int, int] | None:
    for line in text.splitlines():
        normalized = strip_accents(line).upper()
        if not any(label in normalized for label in labels):
            continue
        return parse_admin_time(line)
    return None


def parse_admin_time(value: str) -> tuple[int, int, int] | None:
    match = re.search(
        r"(\d{1,3})\s*A(?:NOS?)?\s*(\d{1,2})\s*M(?:ESES?)?\s*(\d{1,2})\s*D(?:IAS?)?",
        strip_accents(value).upper(),
    )
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def build_observacoes_calculo(record: SicapexParsedRecord) -> str:
    parts = ["Dados de tempo importados da Ficha Cadastro SiCaPEx."]
    if record.tempo_efetivo_servico_apos_ultima:
        parts.append(
            f"Tempo efetivo apos a ultima alteracao: {record.tempo_efetivo_servico_apos_ultima} dias."
        )
    if record.desconto_tempo_servico:
        parts.append(f"Descontos registrados: {len(record.desconto_tempo_servico)}.")
    if record.acrescimos_tempo_servico:
        parts.append(f"Acrescimos registrados: {len(record.acrescimos_tempo_servico)}.")
    parts.append("Calculo final depende de validacao/homologacao humana.")
    return " ".join(parts)


def build_tempo_servico_bruto(record: SicapexParsedRecord) -> dict[str, Any]:
    return scrub_sensitive(
        {
            "datas_praca": record.datas_praca,
            "tempo_efetivo_servico_apos_ultima_dias": record.tempo_efetivo_servico_apos_ultima_dias,
            "descontos": record.desconto_tempo_servico,
            "acrescimos": record.acrescimos_tempo_servico,
            "tempo_servico_anterior": {
                "anos": record.tempo_servico_anterior_anos,
                "meses": record.tempo_servico_anterior_meses,
                "dias": record.tempo_servico_anterior_dias,
            },
            "tempo_servico_publico": {
                "anos": record.tempo_servico_publico_anos,
                "meses": record.tempo_servico_publico_meses,
                "dias": record.tempo_servico_publico_dias,
            },
        }
    )


def build_periodos_servico_sugeridos(record: SicapexParsedRecord) -> list[SicapexPeriodoServicoSugerido]:
    periodos: list[SicapexPeriodoServicoSugerido] = []
    if record.data_praca:
        periodos.append(
            SicapexPeriodoServicoSugerido(
                tipo_registro="vinculo_militar",
                subtipo_registro="data_praca",
                natureza_servico="servico_militar",
                categoria_tempo="computado",
                data_inicio=record.data_praca,
                data_fim=record.datas_praca[0].data_desligamento if record.datas_praca else None,
                computa_tempo=True,
                arregimentado=True,
                documento_referencia=record.documento_praca,
                status_calculo="pendente_validacao",
                om_destino=record.om_atual_nome,
                descricao="Vinculo militar extraido da secao Datas de Praca.",
                payload_json={"tipo_forca": record.tipo_forca, "raw": record.datas_praca[0].raw if record.datas_praca else ""},
            )
        )

    for item in record.movimentacoes:
        if not item.data_inicio:
            continue
        periodos.append(
            SicapexPeriodoServicoSugerido(
                tipo_registro="movimentacao",
                subtipo_registro=item.tipo or "transferencia",
                natureza_servico="servico_militar",
                categoria_tempo="computado",
                data_inicio=item.data_inicio,
                data_fim=item.data_fim,
                computa_tempo=True,
                arregimentado=False,
                status_calculo="pendente_classificacao",
                om_destino=item.om,
                descricao="Movimentacao extraida da Ficha SiCaPEx.",
                payload_json=record_payload_from_dataclass(item),
            )
        )

    for item in record.situacoes_regulamentares:
        if not item.data_inicio:
            continue
        periodos.append(
            SicapexPeriodoServicoSugerido(
                tipo_registro="situacao_regulamentar",
                subtipo_registro=item.situacao or item.motivo or "situacao",
                natureza_servico="servico_militar",
                categoria_tempo="computado",
                data_inicio=item.data_inicio,
                data_fim=item.data_fim,
                computa_tempo=True,
                arregimentado=False,
                status_calculo="pendente_validacao",
                om_destino=item.om,
                descricao="Situacao regulamentar extraida da Ficha SiCaPEx.",
                payload_json=record_payload_from_dataclass(item),
            )
        )

    for item in record.afastamentos:
        if not item.data_inicio:
            continue
        periodos.append(
            SicapexPeriodoServicoSugerido(
                tipo_registro="afastamento",
                subtipo_registro=normalize_event_subtype(item.modalidade),
                natureza_servico="afastamento",
                categoria_tempo="informativo",
                data_inicio=item.data_inicio,
                data_fim=item.data_fim,
                computa_tempo=False,
                arregimentado=False,
                dias_lancados_override=item.quantidade_dias,
                documento_referencia=item.documento,
                status_calculo="informativo_pendente_classificacao",
                descricao="Afastamento informativo extraido da Ficha SiCaPEx.",
                observacoes="Nao classificado automaticamente como TNC.",
                payload_json=record_payload_from_dataclass(item),
            )
        )

    periodos.extend(build_tempo_periodos(record.desconto_tempo_servico, "desconto_tempo"))
    periodos.extend(build_tempo_periodos(record.acrescimos_tempo_servico, "acrescimo_tempo"))
    periodos.extend(build_tempo_anterior_periodos(record))
    return periodos


def build_tempo_periodos(items: list[SicapexTempoServico], tipo: str) -> list[SicapexPeriodoServicoSugerido]:
    periodos: list[SicapexPeriodoServicoSugerido] = []
    for item in items:
        if not item.data_inicio and not item.dias:
            continue
        is_desconto = tipo == "desconto_tempo"
        periodos.append(
            SicapexPeriodoServicoSugerido(
                tipo_registro=tipo,
                subtipo_registro=normalize_event_subtype(item.subtipo or item.tipo or tipo),
                natureza_servico="tempo_nao_computado" if is_desconto else "tempo_adicional",
                categoria_tempo="nao_computado" if is_desconto else "adicional",
                data_inicio=item.data_inicio,
                data_fim=item.data_fim,
                computa_tempo=not is_desconto,
                arregimentado=False,
                dias_lancados_override=item.dias,
                documento_referencia=item.documento,
                status_calculo="sicapex_informado",
                descricao="Tempo informado na secao Tempo de Servico da Ficha SiCaPEx.",
                payload_json=record_payload_from_dataclass(item),
            )
        )
    return periodos


def build_tempo_anterior_periodos(record: SicapexParsedRecord) -> list[SicapexPeriodoServicoSugerido]:
    result: list[SicapexPeriodoServicoSugerido] = []
    if not record.data_praca:
        return result
    anterior_dias = ymd_to_days(
        record.tempo_servico_anterior_anos,
        record.tempo_servico_anterior_meses,
        record.tempo_servico_anterior_dias,
    )
    if anterior_dias:
        result.append(tempo_anterior_periodo("militar", "servico_militar", anterior_dias, record.data_praca))
    publico_dias = ymd_to_days(
        record.tempo_servico_publico_anos,
        record.tempo_servico_publico_meses,
        record.tempo_servico_publico_dias,
    )
    if publico_dias:
        result.append(tempo_anterior_periodo("publico", "servico_publico", publico_dias, record.data_praca))
    return result


def tempo_anterior_periodo(
    subtipo: str,
    natureza: str,
    dias: int,
    data_ref: date | None,
) -> SicapexPeriodoServicoSugerido:
    return SicapexPeriodoServicoSugerido(
        tipo_registro="servico_anterior",
        subtipo_registro=subtipo,
        natureza_servico=natureza,
        categoria_tempo="computado",
        data_inicio=data_ref,
        data_fim=data_ref,
        computa_tempo=True,
        arregimentado=False,
        dias_lancados_override=dias,
        status_calculo="sicapex_informado",
        descricao="Tempo anterior informado pela Ficha SiCaPEx.",
        payload_json={"dias": dias},
    )


def build_pendencias_calculo(record: SicapexParsedRecord) -> list[str]:
    pendencias: list[str] = []
    if not record.data_praca:
        pendencias.append("DATA_PRACA_PENDENTE")
    if not record.tempo_efetivo_servico_apos_ultima_dias:
        pendencias.append("TEMPO_EFETIVO_SICAPEX_PENDENTE")
    if not record.periodos_servico_sugeridos:
        pendencias.append("PERIODOS_SICAPEX_PENDENTES")
    pendencias.extend(item for item in record.pending if item not in pendencias)
    return pendencias


def record_payload_from_dataclass(item: Any) -> dict[str, Any]:
    payload = asdict(item) if is_dataclass(item) else dict(item)
    return scrub_sensitive(record_payload_json(payload))


def record_payload_json(payload: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, date):
            clean[key] = value.isoformat()
        else:
            clean[key] = value
    return clean


def normalize_event_subtype(value: str) -> str:
    normalized = strip_accents(normalize_space(value)).lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return normalized or "nao_classificado"


def ymd_to_days(anos: int, meses: int, dias: int) -> int:
    return int(anos or 0) * 365 + int(meses or 0) * 30 + int(dias or 0)


def parse_raw_rows(lines: list[str]) -> list[dict[str, Any]]:
    return [{"raw": line} for line in data_lines(lines)]


def data_lines(lines: list[str]) -> list[str]:
    ignored = ("Nenhum registro encontrado", "Codigo ", "Modalidade ", "Tipo ", "Dt ", "Data ")
    return [line for line in lines if line and not any(line.startswith(prefix) for prefix in ignored)]


def merge_wrapped_rows(lines: list[str]) -> list[str]:
    rows: list[str] = []
    buffer: list[str] = []
    for line in data_lines(lines):
        if re.match(r"^\d{2,6}\s", line) and buffer:
            rows.append(normalize_space(" ".join(buffer)))
            buffer = [line]
        else:
            buffer.append(line)
    if buffer:
        rows.append(normalize_space(" ".join(buffer)))
    return rows


def record_to_safe_dict(record: SicapexParsedRecord) -> dict[str, Any]:
    data = asdict(record) if is_dataclass(record) else dict(record)
    data.pop("raw_excerpt", None)
    return scrub_sensitive(data)


def scrub_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            normalized = strip_accents(str(key)).lower()
            if any(secret in normalized for secret in SENSITIVE_KEYS):
                continue
            clean[key] = scrub_sensitive(item)
        return clean
    if isinstance(value, list):
        return [scrub_sensitive(item) for item in value]
    if isinstance(value, date):
        return value.isoformat()
    return value


def mask_identity(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) <= 4:
        return "***"
    return f"{digits[:2]}***{digits[-2:]}"


def identity_hash(value: str) -> str:
    import hashlib

    normalized = re.sub(r"\D", "", value or "")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def capture(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, flags=re.I | re.M | re.S)
    return normalize_space(match.group(1)) if match else None


def parse_br_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        day, month, year = [int(part) for part in value.split("/")]
        return date(year, month, day)
    except ValueError:
        return None


def parse_int(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    return int(digits) if digits else None


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def strip_accents(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()


def is_invalid_nome_guerra(value: str) -> bool:
    normalized = strip_accents(value).upper()
    invalid_patterns = [
        r"\bBI\b",
        r"\bNOME\b",
        r"\bB\s+ADM\b",
        r"\bNR\b",
        r"\bNO\b",
        r"\bADIT\b",
        r"\bDT\s+TURMA\b",
        r"\bDE\s+",
        r"\d{2}/\d{2}/\d{4}",
        r"\bQGEX\b",
        r"\bPORT\b",
        r"\bBOLETIM\b",
    ]
    return any(re.search(pattern, normalized) for pattern in invalid_patterns)


def normalize_om_name(value: str) -> str:
    normalized = strip_accents(normalize_space(value)).upper()
    compact = re.sub(r"[^A-Z0-9]+", "", normalized)
    if (
        "BASEADMINISTRATIVADOQGEX" in compact
        or re.search(r"BADM(?:Q|Q2)GE(?:7)?X", compact)
        or re.search(r"BADMQ(?:2)?GE(?:7)?X", compact)
    ):
        return "B Adm QGEx"
    return normalize_space(value)


def normalize_comportamento(value: str) -> str:
    mapping = {
        "BOM": "BOM",
        "OTIMO": "ÓTIMO",
        "EXCEPCIONAL": "EXCEPCIONAL",
        "INSUFICIENTE": "INSUFICIENTE",
    }
    return mapping.get(strip_accents(value).upper(), normalize_space(value).upper())


def expand_posto_grad(value: str) -> str:
    key = strip_accents(normalize_space(value)).lower().replace("º", "o")
    mapping = {
        "3o sgt": "Terceiro-Sargento",
        "2o sgt": "Segundo-Sargento",
        "1o sgt": "Primeiro-Sargento",
        "s ten": "Subtenente",
        "cb": "Cabo",
        "sd": "Soldado",
        "2o ten": "Segundo-Tenente",
        "1o ten": "Primeiro-Tenente",
        "cap": "Capitao",
        "maj": "Major",
        "cel": "Coronel",
    }
    return mapping.get(key, value)
