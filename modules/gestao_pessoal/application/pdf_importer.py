from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any
import unicodedata

import pdfplumber

from modules.gestao_pessoal.application.schemas import MilitarCreate, MilitarUpdate
from modules.gestao_pessoal.application.text_parser import _parse_br_date
from modules.gestao_pessoal.infrastructure.repository import GestaoPessoalRepository
from shared.utils.hashing import sha256_file


FICHA_CADASTRO_SCHEMA_VERSION = "sicapex_ficha_cadastro.v1"


_SECTION_ALIASES = {
    "FICHA CADASTRO SICAPEX": "CABECALHO",
    "DADOS PESSOAIS": "DADOS PESSOAIS",
    "DOCUMENTOS": "DOCUMENTOS",
    "DADOS MEDICOS": "DADOS MEDICOS",
    "DADOS MADICOS": "DADOS MEDICOS",
    "DADOS FUNCIONAIS": "DADOS FUNCIONAIS",
    "OM ATUAL": "OM ATUAL",
    "SITUACAO DO MILITAR": "SITUACAO DO MILITAR",
    "SITUAO DO MILITAR": "SITUACAO DO MILITAR",
    "DOCUMENTOS FUNCIONAIS": "DOCUMENTOS FUNCIONAIS",
    "DADOS INDIVIDUAIS": "DADOS INDIVIDUAIS",
    "CONTATOS": "CONTATOS",
    "DADOS BIOMETRICOS": "DADOS BIOMETRICOS",
    "DATAS DE PRACA": "DATAS DE PRACA",
    "DATAS DE PRAA": "DATAS DE PRACA",
    "ENDERECOS": "ENDERECOS",
    "ENDEREOS": "ENDERECOS",
    "INFORMACOES BANCARIAS": "INFORMACOES BANCARIAS",
    "INFORMAES BANCARIAS": "INFORMACOES BANCARIAS",
    "AFASTAMENTOS": "AFASTAMENTOS",
    "AGREGACOES": "AGREGACOES",
    "AGREGAES": "AGREGACOES",
    "ALTERACOES": "ALTERACOES",
    "ALTERAES": "ALTERACOES",
    "DEPENDENTES": "DEPENDENTES",
    "EXCLUSAO DA FORCA": "EXCLUSAO DA FORCA",
    "EXCLUSO DA FORA": "EXCLUSAO DA FORCA",
    "FUNCOES SENSIVEIS": "FUNCOES SENSIVEIS",
    "FUNES SENSVEIS": "FUNCOES SENSIVEIS",
    "HABILITACOES": "HABILITACOES",
    "HABILITAES": "HABILITACOES",
    "CURSOS ESTAGIOS EM ORGANIZACOES MILITARES": "CURSOS EM OM",
    "CURSOS ESTAGIOS EM ORGANIZAES MILITARES": "CURSOS EM OM",
    "CURSOS ESTAGIOS EM ORGANIZACOES CIVIS": "CURSOS CIVIS",
    "CURSOS ESTAGIOS EM ORGANIZAES CIVIS": "CURSOS CIVIS",
    "INSTRUTOR MONITOR": "INSTRUTOR MONITOR",
    "INSPECOES DE SAUDE": "INSPECOES DE SAUDE",
    "INSPEES DE SADE": "INSPECOES DE SAUDE",
    "JUSTICA E DISCIPLINA": "JUSTICA E DISCIPLINA",
    "JUSTIA E DISCIPLINA": "JUSTICA E DISCIPLINA",
    "MERITO ELOGIOS": "MERITO ELOGIOS",
    "MARITO ELOGIOS": "MERITO ELOGIOS",
    "MERITO MEDALHAS": "MERITO MEDALHAS",
    "MARITO MEDALHAS": "MERITO MEDALHAS",
    "MERITO TRABALHOS UTEIS": "MERITO TRABALHOS UTEIS",
    "MARITO TRABALHOS UTEIS": "MERITO TRABALHOS UTEIS",
    "MOVIMENTACOES": "MOVIMENTACOES",
    "MOVIMENTAES": "MOVIMENTACOES",
    "PASSAGEM A DISPOSICAO": "PASSAGEM A DISPOSICAO",
    "PASSAGEM A DISPOSIO": "PASSAGEM A DISPOSICAO",
    "PNR": "PNR",
    "PROFICIENCIA LINGUISTICA": "PROFICIENCIA LINGUISTICA",
    "PROEFICIENCIA LINGUISTICA": "PROFICIENCIA LINGUISTICA",
    "PROMOCOES": "PROMOCOES",
    "PROMOES": "PROMOCOES",
    "QFE": "QFE",
    "REFORMA": "REFORMA",
    "RESERVA": "RESERVA",
    "DOCUMENTOS DA RESERVA": "DOCUMENTOS DA RESERVA",
    "SITUACOES DIVERSAS": "SITUACOES DIVERSAS",
    "SITUAES DIVERSAS": "SITUACOES DIVERSAS",
    "SITUACOES REGULAMENTARES": "SITUACOES REGULAMENTARES",
    "SITUAES REGULAMENTARES": "SITUACOES REGULAMENTARES",
    "TEMPO DE SERVICO": "TEMPO DE SERVICO",
    "TEMPO DE SERVIO": "TEMPO DE SERVICO",
    "DESCONTO DE TEMPOS DE SERVICOS": "DESCONTOS TEMPO SERVICO",
    "ACRESCIMOS DE TEMPO DE SERVICO": "ACRESCIMOS TEMPO SERVICO",
    "ACRASCIMOS DE TEMPO DE SERVICO": "ACRESCIMOS TEMPO SERVICO",
    "TESTES DE APTIDAO": "TESTES DE APTIDAO",
    "TESTES DE APTIDO": "TESTES DE APTIDAO",
    "COMPOSICOES CORPORAIS": "COMPOSICOES CORPORAIS",
    "COMPOSIES CORPORAIS": "COMPOSICOES CORPORAIS",
    "TAF": "TAF",
    "TAT": "TAT",
}


@dataclass(frozen=True)
class MilitarPdfParseResult:
    parsed_data: dict[str, Any]
    warnings: list[str]
    unmapped_lines: list[str]
    raw_excerpt: str


def extract_text_from_sicapex_pdf(pdf_path: str | Path) -> str:
    path = Path(pdf_path)
    texts: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            texts.append(page.extract_text() or "")
    return "\n".join(texts)


def parse_sicapex_pdf(pdf_path: str | Path) -> MilitarPdfParseResult:
    path = Path(pdf_path)
    result = parse_sicapex_text(extract_text_from_sicapex_pdf(path))
    parsed_data = dict(result.parsed_data)
    pdf_hash = sha256_file(path)
    imported_at = datetime.now(UTC).replace(tzinfo=None)

    parsed_data["ficha_cadastro_pdf_hash"] = pdf_hash
    parsed_data["ficha_cadastro_origem"] = path.name
    parsed_data["ficha_cadastro_importado_em"] = imported_at

    ficha = dict(parsed_data.get("ficha_cadastro_json") or {})
    source = dict(ficha.get("source") or {})
    source.update(
        {
            "filename": path.name,
            "sha256": pdf_hash,
            "imported_at": imported_at.isoformat(timespec="seconds"),
        }
    )
    ficha["source"] = source
    parsed_data["ficha_cadastro_json"] = ficha

    return MilitarPdfParseResult(
        parsed_data=parsed_data,
        warnings=result.warnings,
        unmapped_lines=result.unmapped_lines,
        raw_excerpt=result.raw_excerpt,
    )


def parse_sicapex_text(raw_text: str) -> MilitarPdfParseResult:
    text = _clean_pdf_text(raw_text)
    warnings: list[str] = []
    parsed: dict[str, Any] = {"ativo": True, "observacoes": "Importado de ficha SiCaPEx PDF."}

    parsed["nome_completo"] = _capture(text, r"Nome:\s*(.+)")
    parsed["sexo"] = _parse_sexo(text)
    parsed["estado_civil"] = _parse_estado_civil(text)
    parsed["escolaridade"] = _capture(text, r"Escolaridade:\s*([^\n]+?)(?:\s+Religi\S*:|$)")
    parsed["religiao"] = _capture(text, r"Religi\S*:\s*([^\n]+)")
    parsed["situacao_militar"] = _capture(text, r"Situa\S*o\s+(Carreira/Ativo|Reserva|Reforma|Inativo)")
    parsed["status_servico"] = _capture(
        text,
        r"Situa\S*o\s+(Efetivo pronto|N\S*o Apresentado.*|Adido.*|Comandante.*)",
    )
    parsed["cpf"] = _capture(text, r"CPF:\s*([0-9.\-]+)")
    parsed["pis_pasep"] = _capture(text, r"Pis/Pasep:\s*([0-9]+)")
    parsed["ra"] = _capture(text, r"\bRA:[ \t]*([^\n]*)")
    parsed["identidade_civil"] = _capture(text, r"Idt Civil:\s*([0-9A-Za-z.\-]+)")
    parsed["identidade"] = _capture(
        text,
        r"(?:Documentos Funcionais\s+)?Idt\s+([0-9A-Za-z.\-]+)\s+Prec-CP:",
    )
    parsed["prec_cp"] = _capture(text, r"Prec-CP:\s*([0-9A-Za-z.\-]+)")
    parsed["cp"] = _capture(text, r"\bIdt\s+.*?Prec-CP:.*?\s+CP:\s*([0-9A-Za-z.\-]+)")
    parsed["tipo_sanguineo"] = _capture(text, r"Tp Sangu\S*neo:\s*([^\n]+?)\s+Fator RH:")
    parsed["fator_rh"] = _capture(text, r"Fator RH:\s*([^\n]+?)\s+Doador")
    parsed["autodeclaracao_etnico_racial"] = _capture(
        text,
        r"Autodeclara\S*o\s+\S*tnico-\s*([^\n]+)",
    )
    parsed["posto_graduacao"] = _capture(text, r"Posto/Grad:\s*([^\n]+?)\s+Nome\s+")
    parsed["nome_guerra"] = _capture(text, r"Posto/Grad:.*?\s+Nome\s+(.+?)\s+Dt Turma:")
    parsed["qas_qms"] = _capture(text, r"QAS/QMS/QM\s+(.+)")
    parsed["rm"] = _capture(text, r"RM:\s*([^\n]+?)\s+OM/CODOM:")
    parsed["om"] = _fix_pdf_noise(_capture(text, r"OM/CODOM:\s*(.+?)\s+-\s*[0-9.]+"))
    parsed["local_om"] = _fix_pdf_noise(_capture(text, r"Local da\s+(.+)"))
    if re.search(r"Doador\s+\S*rg\S*os:.*(?:\(X\)\s*Sim|Sim\s+X)", text):
        parsed["doador_orgaos"] = "Sim"
    parsed["email"] = _capture(text, r"E-Mail Pessoal\s+([^\s]+)")
    parsed["celular"] = _capture(text, r"Tel Celular\s+([0-9()+\-\s]+)")

    filiation = _capture(text, r"Filia\S*o\s+(.+?)\s+Naturalidade", flags=re.DOTALL)
    if filiation and " e " in filiation:
        pai, mae = filiation.split(" e ", 1)
        parsed["nome_pai"] = _squash(pai)
        parsed["nome_mae"] = _squash(mae)

    parsed.update(_parse_birth_data(text))
    parsed.update(_parse_title_data(text))
    parsed.update(_parse_dates(text))
    parsed.update(_parse_current_om_data(text))
    parsed.update(_parse_split_functional_data(text, parsed))

    parsed = {key: value for key, value in parsed.items() if value not in ("", None)}
    parsed["ficha_cadastro_json"] = _build_ficha_cadastro_json(text, parsed)
    if not parsed.get("nome_completo"):
        warnings.append("Nome completo nao foi encontrado no PDF SiCaPEx.")
    if not parsed.get("identidade"):
        warnings.append("Identidade funcional nao foi encontrada no PDF SiCaPEx.")
    if not parsed.get("om"):
        warnings.append("OM atual nao foi encontrada no PDF SiCaPEx.")

    return MilitarPdfParseResult(
        parsed_data=parsed,
        warnings=warnings,
        unmapped_lines=[],
        raw_excerpt=text[:1500],
    )


def upsert_militar_from_sicapex_pdf(db, pdf_path: str | Path) -> dict[str, Any]:
    result = parse_sicapex_pdf(pdf_path)
    parsed_data = dict(result.parsed_data)
    repo = GestaoPessoalRepository(db)
    existing = None

    identidade = parsed_data.get("identidade")
    cpf = parsed_data.get("cpf")
    if identidade:
        existing = repo.get_by_identidade(identidade)
    if not existing and cpf:
        existing = repo.get_by_cpf(cpf)

    if existing:
        militar = repo.update(existing.id, MilitarUpdate(**parsed_data))
        action = "updated"
    else:
        militar = repo.create(MilitarCreate(**parsed_data))
        action = "created"

    return {
        "militar": militar,
        "action": action,
        "warnings": result.warnings,
        "unmapped_lines": result.unmapped_lines,
        "raw_excerpt": result.raw_excerpt,
    }


def _clean_pdf_text(raw_text: str) -> str:
    lines = []
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.fullmatch(r"[0-9.\- ]+", line):
            continue
        if line in {"dt:", "I"}:
            continue
        if re.match(r"^P\S*gina\s+\d+\s+de\s+\d+", line, flags=re.IGNORECASE):
            continue
        lines.append(line)
    return "\n".join(lines)


def _capture(text: str, pattern: str, *, flags: int = 0) -> str | None:
    match = re.search(pattern, text, flags)
    if not match:
        return None
    return _squash(match.group(1))


def _squash(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" :-")


def _parse_date(value: str | None) -> str | None:
    return _parse_br_date(value or "")


def _parse_sexo(text: str) -> str | None:
    direct = _capture(text, r"Sexo:\s*(Masculino|Feminino|MASCULINO|FEMININO)")
    if direct:
        return direct.title()
    match = re.search(r"\b(MASCULINO|FEMININO)\b", text[:800], flags=re.IGNORECASE)
    return match.group(1).title() if match else None


def _parse_estado_civil(text: str) -> str | None:
    direct = _capture(
        text,
        r"Estado Civil:\s*(Casado|Solteiro|Divorciado|Vi\S*vo|CASADO|SOLTEIRO|DIVORCIADO|VI\S*VO)",
    )
    if direct:
        return direct.title()
    match = re.search(
        r"\b(CASADO|SOLTEIRO|DIVORCIADO|VI\S*VO)\b",
        text[:1000],
        flags=re.IGNORECASE,
    )
    return match.group(1).title() if match else None


def _parse_birth_data(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    result["local_nascimento"] = _capture(text, r"Cidade:\s*([^\n]+)")
    result["data_nascimento"] = _parse_date(_capture(text, r"Dt Nasc:\s*([0-9/]+)"))
    result["nacionalidade"] = _capture(text, r"Nacionalidad\s+(.+)")
    return result


def _parse_title_data(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    match = re.search(r"N\S*mero:\s*([0-9.]+)\s+Zona:\s*([0-9.]+)\s+Se\S*o:\s*([0-9.]+)", text)
    if match:
        result["titulo_numero"] = match.group(1)
        result["titulo_zona"] = match.group(2)
        result["titulo_secao"] = match.group(3)
    return result


def _parse_dates(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    result["data_turma"] = _parse_date(_capture(text, r"Dt Turma:\s*([0-9/]+)"))
    result["ultima_promocao"] = _parse_date(_capture(text, r"Dt \S*ltima\s*([0-9/]+)"))
    result["apresentacao_om"] = _parse_date(_capture(text, r"Dt In\S*cio\s*([0-9/]+)"))
    data_praca = _parse_date(
        _capture(text, r"Datas de Pra\S*a.*?Dt Pra\S*a.*?\n([0-9/]+)", flags=re.DOTALL)
    )
    if data_praca:
        result["data_praca"] = data_praca
        result["data_incorporacao"] = data_praca
    return result


def _parse_current_om_data(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    universo = _capture(text, r"Universo:\s*(ATIVO|INATIVO|RESERVA|REFORMADO)")
    if universo:
        result["ativo"] = universo.upper() == "ATIVO"

    fallback = re.search(
        r"RM:\s*OM/CODOM:\s*Dt In\S*cio\s*\n"
        r"(?P<local>[^\n]+)\n"
        r"(?P<rm>.+?RM)\s+(?P<om>.+?)\s+-\s*(?P<codom>[0-9.]+)\s+(?P<inicio>[0-9/]+)",
        text,
        flags=re.DOTALL,
    )
    if fallback:
        result["local_om"] = _fix_pdf_noise(fallback.group("local"))
        result["rm"] = _squash(fallback.group("rm"))
        result["om"] = _fix_pdf_noise(fallback.group("om"))
        result["apresentacao_om"] = _parse_date(fallback.group("inicio"))

    return result


def _parse_split_functional_data(text: str, parsed: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    match = re.search(
        r"Posto/Grad:\s*.*?Dt \S*ltima\s*\n"
        r"(?:Nome Dt Turma:\s*\n)?"
        r"(?P<ultima>[0-9/]+)\s+QAS/QMS/QM\s*\n"
        r"(?P<posto>\S+)\s+(?P<nome>.+?)\s+(?P<turma>[0-9/]+)\s*\n"
        r"(?P<qas>[^\n]+)",
        text,
        flags=re.DOTALL,
    )
    if not match:
        return result

    if not parsed.get("ultima_promocao"):
        result["ultima_promocao"] = _parse_date(match.group("ultima"))
    posto_atual = str(parsed.get("posto_graduacao") or "")
    if not posto_atual or posto_atual.lower().startswith("dt "):
        result["posto_graduacao"] = _squash(match.group("posto"))
    if not parsed.get("nome_guerra"):
        result["nome_guerra"] = _squash(match.group("nome"))
    if not parsed.get("data_turma"):
        result["data_turma"] = _parse_date(match.group("turma"))
    if not parsed.get("qas_qms"):
        result["qas_qms"] = _squash(match.group("qas"))
    return result


def _build_ficha_cadastro_json(text: str, parsed_fields: dict[str, Any]) -> dict[str, Any]:
    lines = text.splitlines()
    sections = _group_lines_by_section(lines)
    return {
        "schema_version": FICHA_CADASTRO_SCHEMA_VERSION,
        "source": {
            "system": "SiCaPEx",
            "document_type": "FICHA CADASTRO",
            "format": "pdf_text",
        },
        "coverage": {
            "line_count": len(lines),
            "section_count": len(sections),
            "unclassified_line_count": len(sections.get("CABECALHO", [])),
        },
        "fields": _serializable_fields(parsed_fields),
        "sections": sections,
        "tables": _parse_known_tables(sections),
    }


def _group_lines_by_section(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"CABECALHO": []}
    current = "CABECALHO"
    for line in lines:
        section = _canonical_section_name(line)
        if section:
            current = section
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {name: values for name, values in sections.items() if values or name != "CABECALHO"}


def _canonical_section_name(line: str) -> str | None:
    key = _normalize_lookup(line)
    if key in _SECTION_ALIASES:
        return _SECTION_ALIASES[key]
    return None


def _normalize_lookup(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.upper()).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^A-Z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _serializable_fields(parsed_fields: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in parsed_fields.items():
        if key.startswith("ficha_cadastro_"):
            continue
        if value in (None, ""):
            continue
        if isinstance(value, datetime):
            result[key] = value.isoformat(timespec="seconds")
        else:
            result[key] = value
    return result


def _parse_known_tables(sections: dict[str, list[str]]) -> dict[str, Any]:
    return {
        "afastamentos": _parse_afastamentos(sections.get("AFASTAMENTOS", [])),
        "alteracoes": _parse_raw_table(sections.get("ALTERACOES", [])),
        "dependentes": _parse_raw_table(sections.get("DEPENDENTES", [])),
        "habilitacoes": _parse_raw_table(sections.get("HABILITACOES", []) + sections.get("CURSOS EM OM", [])),
        "movimentacoes": _parse_movimentacoes(sections.get("MOVIMENTACOES", [])),
        "promocoes": _parse_promocoes(sections.get("PROMOCOES", [])),
        "situacoes_regulamentares": _parse_raw_table(sections.get("SITUACOES REGULAMENTARES", [])),
        "acrescimos_tempo_servico": _parse_raw_table(sections.get("ACRESCIMOS TEMPO SERVICO", [])),
        "taf": _parse_raw_table(sections.get("TAF", [])),
        "tat": _parse_raw_table(sections.get("TAT", [])),
    }


def _parse_raw_table(lines: list[str]) -> list[dict[str, str]]:
    return [{"raw": line} for line in _data_lines(lines)]


def _parse_afastamentos(lines: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in _data_lines(lines):
        dates = list(re.finditer(r"\d{2}/\d{2}/\d{4}", line))
        if len(dates) < 2:
            rows.append({"raw": line})
            continue
        before = line[: dates[0].start()].strip()
        modalidade = before
        quantidade = None
        quantity_match = re.search(r"(.+?)\s+(\d+)$", before)
        if quantity_match:
            modalidade = quantity_match.group(1)
            quantidade = int(quantity_match.group(2))
        rows.append(
            {
                "modalidade": _squash(modalidade),
                "quantidade_dias": quantidade,
                "data_inicio": _parse_date(dates[0].group(0)),
                "data_fim": _parse_date(dates[1].group(0)),
                "documento": _squash(line[dates[1].end() :]),
                "raw": line,
            }
        )
    return rows


def _parse_movimentacoes(lines: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    buffer: list[str] = []
    for line in _data_lines(lines):
        if re.match(r"^\d{2,4}\s", line) and buffer:
            rows.append({"raw": _squash(" ".join(buffer))})
            buffer = [line]
        else:
            buffer.append(line)
    if buffer:
        rows.append({"raw": _squash(" ".join(buffer))})
    return rows


def _parse_promocoes(lines: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    posto_pattern = r"(Asp|2\S*\s*Ten|1\S*\s*Ten|Cap|Maj|Ten\s*Cel|Cel)"
    for line in _data_lines(lines):
        match = re.search(rf"^(?P<tipo>.+?)\s+(?P<posto>{posto_pattern})\s+(?P<data>\d{{2}}/\d{{2}}/\d{{4}})\s+(?P<doc>.+)$", line)
        if not match:
            rows.append({"raw": line})
            continue
        rows.append(
            {
                "tipo": _squash(match.group("tipo")),
                "posto_graduacao": _squash(match.group("posto")),
                "data_promocao": _parse_date(match.group("data")) or match.group("data"),
                "documento": _squash(match.group("doc")),
                "raw": line,
            }
        )
    return rows


def _data_lines(lines: list[str]) -> list[str]:
    ignored_prefixes = (
        "Ano ",
        "Codigo ",
        "Modalidade ",
        "Tipo ",
        "REG ",
        "Nr ",
        "N ",
        "No ",
        "Nome Natureza ",
        "Nenhum registro encontrado",
    )
    return [
        line
        for line in lines
        if line and not any(line.startswith(prefix) for prefix in ignored_prefixes)
    ]


def _fix_pdf_noise(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.replace("QGE7x", "QGEx")
    value = re.sub(r"\s+[1279]$", "", value)
    return value.strip()
