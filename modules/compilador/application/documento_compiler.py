from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from xml.sax.saxutils import escape
import json
import zipfile
from xml.etree import ElementTree as ET

from infra.persistence.models import CalculoTempoServicoModel, MilitarModel
from modules.compilador.application.document_template_classifier import (
    EXECUTABLE_TEMPLATE,
    classify_document_template,
)
from shared.utils.hashing import sha256_file
from shared.utils.strings import slugify_filename


DOCUMENTO_DECLARACAO_SERVICO_MILITAR = "DECLARACAO_SERVICO_MILITAR"
DOCUMENTO_CTSM = "CTSM"
OUTPUT_MODE_FULL = "full"
OUTPUT_MODE_ODT = "odt"

TEMPLATE_SOURCE_INTERNAL_DEFAULT = "INTERNAL_DEFAULT"
TEMPLATE_SOURCE_UPLOADED_EXECUTABLE = "UPLOADED_EXECUTABLE_TEMPLATE"
TEMPLATE_SOURCE_DECLARACAO_FLAGS = "UPLOADED_DECLARACAO_FLAG_TEMPLATE"
TEMPLATE_SOURCE_VISUAL_REFERENCE = "VISUAL_REFERENCE_ONLY"
TEMPLATE_SOURCE_INVALID = "INVALID_TEMPLATE"

DECLARACAO_FLAG_NAMES = (
    "INSTITUICAO_ENSINO",
    "ARTIGO_MILITAR",
    "TRATAMENTO",
    "NOME_COMPLETO",
    "NOME_GUERRA",
    "POSTO_GRADUACAO",
    "GENERO_BRASILEIRO",
    "IDENTIDADE",
    "CPF",
    "RA",
    "OM",
    "ATO_SERVICO",
    "DATA_SERVICO",
    "SITUACAO_AUSENCIA",
    "REFERENCIA_ALUNO",
    "DATA_EXTENSO",
    "ASSINATURA_NOME",
    "ASSINATURA_FUNCAO",
)

SISGES_DOCUMENT_MARKER_MAP = {
    "NOME_COMPLETO": "NOME_COMPLETO",
    "NOME_GUERRA": "NOME_GUERRA",
    "POSTO_GRADUACAO": "POSTO_GRADUACAO",
    "IDENTIDADE": "IDENTIDADE",
    "CPF": "CPF",
    "OM": "OM",
    "ASSINATURA_NOME": "ASSINATURA_NOME",
    "ASSINATURA_FUNCAO": "ASSINATURA_FUNCAO",
    "DATA_LOCAL": "DATA_EXTENSO",
}


@dataclass(slots=True)
class DocumentoCompilerResult:
    document_type: str
    slug: str
    output_odt_path: Path
    package_path: Path | None
    validation_path: Path
    justification_path: Path
    variables_path: Path
    compiler_run_path: Path
    manifest_path: Path
    variables: dict
    validations: list[str]
    warnings: list[str]
    errors: list[str]
    template_sha256: str | None
    template_source: str


class DocumentoCompiler:
    def __init__(self, db):
        self.db = db

    def compile(
        self,
        *,
        document_type: str,
        militar_id: int,
        output_dir: Path,
        template_path: Path | None = None,
        output_mode: str = OUTPUT_MODE_FULL,
        owner_user_id: str | None = None,
        calculo_id: int | None = None,
        declaracao_context: dict | None = None,
        template_mode: str | None = None,
    ) -> DocumentoCompilerResult:
        document_type = _normalize_document_type(document_type)
        output_mode = _normalize_output_mode(output_mode)
        output_dir.mkdir(parents=True, exist_ok=True)

        militar = self._get_militar(militar_id)
        calculo = self._get_calculo(document_type=document_type, militar_id=militar_id, calculo_id=calculo_id)
        variables = self._build_variables(
            document_type=document_type,
            militar=militar,
            calculo=calculo,
            declaracao_context=declaracao_context,
        )
        validations: list[str] = ["OK_MILITAR_IDENTIFIED"]
        warnings: list[str] = []
        errors: list[str] = []

        template_source = TEMPLATE_SOURCE_INTERNAL_DEFAULT
        template_sha256: str | None = None
        template_validations: list[str] = ["OK_DEFAULT_TEMPLATE_USED"]
        executable_template = False
        if template_path:
            template_sha256 = sha256_file(template_path)
            classification = classify_document_template(template_path)
            template_validations = classification.validations
            if classification.classification == EXECUTABLE_TEMPLATE:
                template_source = TEMPLATE_SOURCE_UPLOADED_EXECUTABLE
                executable_template = True
            elif document_type == DOCUMENTO_DECLARACAO_SERVICO_MILITAR and _has_declaracao_flags(template_path):
                template_source = TEMPLATE_SOURCE_DECLARACAO_FLAGS
                template_validations = ["OK_DECLARACAO_FLAG_TEMPLATE_USED"]
                executable_template = True
            elif classification.classification == "INVALID_TEMPLATE":
                errors.append("ERR_TEMPLATE_ODT_INVALID")
                template_source = TEMPLATE_SOURCE_INVALID
            elif document_type == DOCUMENTO_DECLARACAO_SERVICO_MILITAR and template_mode == "odt_flags":
                errors.append("ERR_DECLARACAO_FLAG_TEMPLATE_INVALID")
                template_source = TEMPLATE_SOURCE_VISUAL_REFERENCE
            else:
                template_source = TEMPLATE_SOURCE_VISUAL_REFERENCE
                warnings.append("WARN_TEMPLATE_VISUAL_REFERENCE_ONLY")
        validations.extend(template_validations)

        variables["template"] = {
            "provided_by_user": template_path is not None,
            "source": template_source,
            "sha256": template_sha256,
            "used": executable_template,
        }

        if document_type == DOCUMENTO_CTSM:
            if calculo is None:
                errors.append("ERR_APPROVED_TIME_SNAPSHOT_MISSING")
            else:
                validations.append("OK_CTSM_APPROVED_SNAPSHOT_USED")
                validations.append("OK_TEMPO_SERVICO_SOURCE_TRACEABLE")
        else:
            validations.append("OK_DECLARACAO_DATA_FROM_GESTAO_PESSOAL")
            warnings.extend(_declaracao_context_warnings(variables))

        slug = slugify_filename(
            f"{document_type}_{militar.posto_graduacao or ''}_{militar.nome_guerra or militar.nome_completo}",
            fallback=f"{document_type.lower()}-{militar.id}",
        )
        output_odt_path = output_dir / f"{slug}.odt"
        if executable_template and template_path:
            replacements = _document_replacements(document_type=document_type, variables=variables)
            _write_odt_from_template(template_path, output_odt_path, replacements=replacements)
            validations.append("OK_UPLOADED_TEMPLATE_RENDERED")
        else:
            body_xml = self._document_body_xml(document_type=document_type, variables=variables)
            _write_odt(output_odt_path, body_xml=body_xml)
        validations.append("OK_ODT_GENERATED")
        leftovers = _find_leftover_placeholders(output_odt_path)
        if leftovers:
            errors.append("ERR_TEMPLATE_PLACEHOLDER_LEFTOVER")
            variables["template_leftovers"] = leftovers
        else:
            validations.append("OK_TEMPLATE_PLACEHOLDERS_REPLACED")

        validation_path = output_dir / "validacao.txt"
        justification_path = output_dir / "justificativa.txt"
        variables_path = output_dir / "variables.json"
        compiler_run_path = output_dir / "compiler_run.json"
        manifest_path = output_dir / "manifest.json"
        package_path = output_dir / f"{slug}_pacote.zip" if output_mode == OUTPUT_MODE_FULL else None

        variables["validations"] = validations
        variables["warnings"] = warnings
        variables["errors"] = errors
        _write_json(variables_path, variables)
        validation_path.write_text(_validation_text(validations, warnings, errors), encoding="utf-8")
        justification_path.write_text(_justification_text(document_type, variables), encoding="utf-8")
        compiler_run = {
            "run_id": str(uuid4()),
            "trace_id": str(uuid4()),
            "status": "FALHOU" if errors else ("CONCLUIDO_COM_PENDENCIAS" if warnings else "CONCLUIDO"),
            "tipo_documento": document_type,
            "militar_id": militar.id,
            "nome_militar_snapshot": militar.nome_completo,
            "identidade_snapshot": militar.identidade,
            "template_source": template_source,
            "warnings": warnings,
            "errors": errors,
            "outputs": {"odt": output_odt_path.name},
            "created_by_user_id": owner_user_id,
            "generated_at": _now_iso(),
        }
        _write_json(compiler_run_path, compiler_run)

        manifest = _manifest_payload(
            document_type=document_type,
            militar=militar,
            files=[output_odt_path, validation_path, justification_path, variables_path, compiler_run_path],
            validations=validations,
            warnings=warnings,
            errors=errors,
            package_mode=output_mode,
        )
        _write_json(manifest_path, manifest)

        if package_path:
            _write_zip(
                package_path,
                [
                    (output_odt_path, output_odt_path.name),
                    (validation_path, "validacao.txt"),
                    (justification_path, "justificativa.txt"),
                    (variables_path, "variables.json"),
                    (compiler_run_path, "compiler_run.json"),
                    (manifest_path, "manifest.json"),
                ],
            )

        return DocumentoCompilerResult(
            document_type=document_type,
            slug=slug,
            output_odt_path=output_odt_path,
            package_path=package_path,
            validation_path=validation_path,
            justification_path=justification_path,
            variables_path=variables_path,
            compiler_run_path=compiler_run_path,
            manifest_path=manifest_path,
            variables=variables,
            validations=validations,
            warnings=warnings,
            errors=errors,
            template_sha256=template_sha256,
            template_source=template_source,
        )

    def _get_militar(self, militar_id: int) -> MilitarModel:
        militar = self.db.get(MilitarModel, militar_id)
        if not militar:
            raise ValueError("ERR_MILITAR_NOT_FOUND")
        return militar

    def _get_calculo(
        self,
        *,
        document_type: str,
        militar_id: int,
        calculo_id: int | None,
    ) -> CalculoTempoServicoModel | None:
        if document_type != DOCUMENTO_CTSM:
            return None
        query = self.db.query(CalculoTempoServicoModel).filter(
            CalculoTempoServicoModel.militar_id == militar_id,
        )
        if calculo_id is not None:
            query = query.filter(CalculoTempoServicoModel.id == calculo_id)
        return query.order_by(CalculoTempoServicoModel.referencia_data.desc()).first()

    def _build_variables(
        self,
        *,
        document_type: str,
        militar: MilitarModel,
        calculo: CalculoTempoServicoModel | None,
        declaracao_context: dict | None,
    ) -> dict:
        assinatura = {
            "nome": _clean_context_value(declaracao_context, "assinatura_nome") or "SIGNATARIO RESPONSAVEL - Cel",
            "funcao": _clean_context_value(declaracao_context, "assinatura_funcao") or "Cmt B Adm QGEx",
        }
        declaracao = _build_declaracao_context(militar=militar, assinatura=assinatura, payload=declaracao_context or {})
        variables = {
            "schema_version": "documento-compilador-v1",
            "tipo_documento": document_type,
            "militar": {
                "id": militar.id,
                "nome_completo": militar.nome_completo,
                "nome_guerra": militar.nome_guerra,
                "posto_graduacao": militar.posto_graduacao,
                "identidade": militar.identidade,
                "cpf": militar.cpf,
                "om": militar.om,
                "data_praca": militar.data_praca.isoformat() if militar.data_praca else None,
                "comportamento": militar.comportamento,
                "qas_qms": militar.qas_qms,
            },
            "assinatura": assinatura,
            "declaracao": declaracao,
            "fonte_dados": "GESTAO_PESSOAL_DB",
        }
        if calculo:
            variables["tempo_servico"] = {
                "calculo_id": calculo.id,
                "referencia_data": calculo.referencia_data.isoformat(),
                "tempo_computado": _tempo_dict(calculo.tempo_computado_anos, calculo.tempo_computado_meses, calculo.tempo_computado_dias),
                "tempo_total": _tempo_dict(calculo.tempo_total_anos, calculo.tempo_total_meses, calculo.tempo_total_dias),
                "origem": "CALCULO_TEMPO_APROVADO",
            }
        else:
            variables["tempo_servico"] = None
        return variables

    def _document_body_xml(self, *, document_type: str, variables: dict) -> str:
        militar = variables["militar"]
        assinatura = variables["assinatura"]
        if document_type == DOCUMENTO_CTSM:
            tempo = variables.get("tempo_servico") or {}
            texto = (
                "Certifica-se, para fins administrativos, o tempo de serviço militar "
                f"apurado para {militar.get('nome_completo') or ''}, conforme snapshot "
                "rastreável do módulo de cálculo de tempo."
            )
            tempo_lines = [
                "Tempo de serviço",
                f"Referência: {tempo.get('referencia_data') or 'pendente'}",
                f"Tempo computado: {_format_tempo(tempo.get('tempo_computado'))}",
                f"Tempo total: {_format_tempo(tempo.get('tempo_total'))}",
            ]
            title = "CERTIDÃO DE TEMPO DE SERVIÇO MILITAR"
        else:
            texto = (
                "Declaro, para os fins que se fizerem necessários, que o militar abaixo "
                "identificado consta nos registros da Gestão de Pessoal do SISGES."
            )
            tempo_lines = []
            title = "DECLARAÇÃO DE SERVIÇO MILITAR"

        lines = [
            _p("MINISTÉRIO DA DEFESA", "Header"),
            _p("EXÉRCITO BRASILEIRO", "Header"),
            _p(title, "Title"),
            _p("", "Text"),
            _p(f"Nome: {militar.get('nome_completo') or ''}", "Text"),
            _p(f"Posto/Graduação: {militar.get('posto_graduacao') or ''}", "Text"),
            _p(f"Identidade: {militar.get('identidade') or ''}", "Text"),
            _p(f"OM: {militar.get('om') or ''}", "Text"),
            _p("", "Text"),
            _p(texto, "Text"),
            *[_p(line, "Text") for line in tempo_lines],
            _p("", "Text"),
            _p(f"Brasília/DF, {_today_pt()}", "Center"),
            _p("", "Center"),
            _p("", "Center"),
            _p(assinatura["nome"], "Center"),
            _p(assinatura["funcao"], "Center"),
        ]
        return "".join(lines)


def _normalize_document_type(value: str) -> str:
    normalized = (value or "").strip().upper()
    if normalized in {"CTSM", "CERTIDAO_TEMPO_SERVICO_MILITAR"}:
        return DOCUMENTO_CTSM
    return DOCUMENTO_DECLARACAO_SERVICO_MILITAR


def _normalize_output_mode(value: str) -> str:
    normalized = (value or OUTPUT_MODE_FULL).strip().lower()
    if normalized in {"odt", "single", "somente_odt"}:
        return OUTPUT_MODE_ODT
    return OUTPUT_MODE_FULL


def _has_declaracao_flags(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path, "r") as odt:
            combined = "\n".join(
                odt.read(name).decode("utf-8", errors="ignore")
                for name in ("content.xml", "styles.xml")
                if name in odt.namelist()
            )
    except Exception:
        return False
    return any(flag_name in combined for flag_name in DECLARACAO_FLAG_NAMES)


def _document_replacements(*, document_type: str, variables: dict) -> dict[str, str]:
    militar = variables["militar"]
    assinatura = variables["assinatura"]
    declaracao = variables.get("declaracao") or {}
    replacements = {
        "NOME_COMPLETO": militar.get("nome_completo") or "",
        "NOME_GUERRA": militar.get("nome_guerra") or "",
        "POSTO_GRADUACAO": militar.get("posto_graduacao") or "",
        "IDENTIDADE": militar.get("identidade") or "",
        "CPF": militar.get("cpf") or "",
        "RA": militar.get("ra") or "",
        "OM": militar.get("om") or "",
        "ASSINATURA_NOME": assinatura.get("nome") or "",
        "ASSINATURA_FUNCAO": assinatura.get("funcao") or "",
        "DATA_EXTENSO": declaracao.get("data_extenso") or _today_pt_extenso(),
    }
    if document_type == DOCUMENTO_DECLARACAO_SERVICO_MILITAR:
        replacements.update(
            {
                "INSTITUICAO_ENSINO": declaracao.get("instituicao_ensino") or "",
                "ARTIGO_MILITAR": declaracao.get("artigo_militar") or "",
                "TRATAMENTO": declaracao.get("tratamento") or "",
                "GENERO_BRASILEIRO": declaracao.get("genero_brasileiro") or "",
                "ATO_SERVICO": declaracao.get("ato_servico") or "",
                "DATA_SERVICO": declaracao.get("data_servico") or "",
                "SITUACAO_AUSENCIA": declaracao.get("situacao_ausencia") or "",
                "REFERENCIA_ALUNO": declaracao.get("referencia_aluno") or "",
            },
        )
    tempo = variables.get("tempo_servico")
    replacements["TEXTO_DOCUMENTO"] = _texto_documento(document_type, variables)
    replacements["TEMPO_SERVICO"] = _tempo_template_text(tempo)
    return replacements


def _build_declaracao_context(*, militar: MilitarModel, assinatura: dict, payload: dict) -> dict:
    female = _is_female(militar.sexo)
    return {
        "instituicao_ensino": _clean_context_value(payload, "instituicao_ensino") or "instituição de ensino",
        "artigo_militar": _clean_context_value(payload, "artigo_militar") or ("a" if female else "o"),
        "tratamento": _clean_context_value(payload, "tratamento") or ("Senhora" if female else "Senhor"),
        "genero_brasileiro": _clean_context_value(payload, "genero_brasileiro") or ("a" if female else "o"),
        "ato_servico": _clean_context_value(payload, "ato_servico") or ("designada" if female else "designado"),
        "data_servico": _clean_context_value(payload, "data_servico") or _date_to_br(militar.data_praca) or _today_pt(),
        "situacao_ausencia": _clean_context_value(payload, "situacao_ausencia") or ("impossibilitada" if female else "impossibilitado"),
        "referencia_aluno": _clean_context_value(payload, "referencia_aluno") or ("da referida aluna" if female else "do referido aluno"),
        "data_extenso": _clean_context_value(payload, "data_extenso") or _today_pt_extenso(),
        "assinatura_nome": assinatura["nome"],
        "assinatura_funcao": assinatura["funcao"],
        "defaulted_fields": _defaulted_declaracao_fields(militar=militar, payload=payload),
    }


def _defaulted_declaracao_fields(*, militar: MilitarModel, payload: dict) -> list[str]:
    fields: list[str] = []
    for key in ("instituicao_ensino", "data_servico"):
        if not _clean_context_value(payload, key):
            fields.append(key)
    if not militar.cpf:
        fields.append("cpf")
    return fields


def _declaracao_context_warnings(variables: dict) -> list[str]:
    warnings: list[str] = []
    for field in (variables.get("declaracao") or {}).get("defaulted_fields") or []:
        warnings.append(f"WARN_DECLARACAO_FIELD_DEFAULTED_{field.upper()}")
    return warnings


def _clean_context_value(payload: dict | None, key: str) -> str:
    value = (payload or {}).get(key)
    if value is None:
        return ""
    return str(value).strip()


def _is_female(value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    return normalized.startswith("f") or normalized in {"mulher", "feminino"}


def _date_to_br(value) -> str:
    if not value:
        return ""
    return value.strftime("%d/%m/%Y")


def _today_pt_extenso() -> str:
    now = datetime.now(UTC)
    meses = [
        "janeiro",
        "fevereiro",
        "março",
        "abril",
        "maio",
        "junho",
        "julho",
        "agosto",
        "setembro",
        "outubro",
        "novembro",
        "dezembro",
    ]
    return f"{now.day} de {meses[now.month - 1]} de {now.year}."


def _texto_documento(document_type: str, variables: dict) -> str:
    militar = variables["militar"]
    if document_type == DOCUMENTO_CTSM:
        return (
            "Certifica-se, para fins administrativos, o tempo de serviço militar "
            f"apurado para {militar.get('nome_completo') or ''}, conforme snapshot "
            "rastreável do módulo de cálculo de tempo."
        )
    return (
        "Declaro, para os fins que se fizerem necessários, que o militar identificado "
        "consta nos registros da Gestão de Pessoal do SISGES."
    )


def _tempo_template_text(tempo: dict | None) -> str:
    if not tempo:
        return ""
    return "\n".join(
        [
            f"Referência: {tempo.get('referencia_data') or 'pendente'}",
            f"Tempo computado: {_format_tempo(tempo.get('tempo_computado'))}",
            f"Tempo total: {_format_tempo(tempo.get('tempo_total'))}",
        ],
    )


def _tempo_dict(anos: int, meses: int, dias: int) -> dict:
    return {"anos": anos, "meses": meses, "dias": dias, "display": f"{anos:02d}a{meses:02d}m{dias:02d}d"}


def _format_tempo(value: dict | None) -> str:
    if not value:
        return "pendente"
    return value.get("display") or f"{value.get('anos', 0):02d}a{value.get('meses', 0):02d}m{value.get('dias', 0):02d}d"


def _p(text: str, style: str) -> str:
    return f'<text:p text:style-name="{style}">{escape(text)}</text:p>'


def _write_odt(path: Path, *, body_xml: str) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as odt:
        odt.writestr("mimetype", "application/vnd.oasis.opendocument.text", compress_type=zipfile.ZIP_STORED)
        odt.writestr("content.xml", _content_xml(body_xml))
        odt.writestr("styles.xml", _styles_xml())
        odt.writestr("META-INF/manifest.xml", _manifest_xml())
        odt.writestr("meta.xml", _meta_xml())


def _write_odt_from_template(template_path: Path, output_path: Path, *, replacements: dict[str, str]) -> None:
    xml_replacements = _placeholder_replacements(replacements)
    with zipfile.ZipFile(template_path, "r") as source:
        entries = {info.filename: source.read(info.filename) for info in source.infolist()}

    for xml_name in ("content.xml", "styles.xml"):
        if xml_name in entries:
            entries[xml_name] = _replace_placeholders_in_xml(entries[xml_name], xml_replacements)

    with zipfile.ZipFile(output_path, "w") as output:
        if "mimetype" in entries:
            output.writestr(
                "mimetype",
                entries["mimetype"],
                compress_type=zipfile.ZIP_STORED,
            )
        for name, data in entries.items():
            if name == "mimetype":
                continue
            output.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)


def _placeholder_replacements(replacements: dict[str, str]) -> dict[str, str]:
    payload: dict[str, str] = {}
    for key, value in replacements.items():
        safe_value = value or ""
        payload[f"[{key}]"] = safe_value
        if key in SISGES_DOCUMENT_MARKER_MAP:
            payload[f"[[SISGES:{key}]]"] = safe_value
    for sisges_key, value_key in SISGES_DOCUMENT_MARKER_MAP.items():
        if value_key in replacements:
            payload[f"[[SISGES:{sisges_key}]]"] = replacements.get(value_key) or ""
    return payload


def _replace_placeholders_in_xml(xml_bytes: bytes, replacements: dict[str, str]) -> bytes:
    root = ET.fromstring(xml_bytes)
    for placeholder, value in replacements.items():
        _replace_placeholder_in_tree(root, placeholder, value)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _replace_placeholder_in_tree(root: ET.Element, placeholder: str, value: str) -> None:
    while True:
        segments = _text_segments(root)
        full_text = "".join(segment["text"] for segment in segments)
        start = full_text.find(placeholder)
        if start < 0:
            return
        end = start + len(placeholder)
        overlaps = [
            segment
            for segment in segments
            if segment["start"] < end and segment["end"] > start
        ]
        if not overlaps:
            return
        first = overlaps[0]
        last = overlaps[-1]
        inner_start = start + 1
        inner_end = end - 1
        target = max(
            overlaps,
            key=lambda segment: max(0, min(segment["end"], inner_end) - max(segment["start"], inner_start)),
        )
        before = first["text"][: max(0, start - first["start"])]
        after = last["text"][max(0, end - last["start"]) :]
        for segment in overlaps:
            _set_segment_text(segment, "")
        if target is first and target is last:
            _set_segment_text(target, before + value + after)
        elif target is first:
            _set_segment_text(target, before + value)
            _set_segment_text(last, after)
        elif target is last:
            _set_segment_text(first, before)
            _set_segment_text(target, value + after)
        else:
            _set_segment_text(first, before)
            _set_segment_text(target, value)
            _set_segment_text(last, after)


def _text_segments(root: ET.Element) -> list[dict]:
    segments: list[dict] = []
    cursor = 0

    def append(element: ET.Element, field: str) -> None:
        nonlocal cursor
        text = getattr(element, field) or ""
        if text:
            start = cursor
            cursor += len(text)
            segments.append(
                {
                    "element": element,
                    "field": field,
                    "text": text,
                    "start": start,
                    "end": cursor,
                },
            )

    def walk(element: ET.Element) -> None:
        append(element, "text")
        for child in list(element):
            walk(child)
            append(child, "tail")

    walk(root)
    return segments


def _set_segment_text(segment: dict, value: str) -> None:
    setattr(segment["element"], segment["field"], value)


def _find_leftover_placeholders(path: Path) -> list[str]:
    leftovers: set[str] = set()
    with zipfile.ZipFile(path, "r") as odt:
        for name in ("content.xml", "styles.xml"):
            if name not in odt.namelist():
                continue
            text = _extract_xml_text(odt.read(name))
            for flag in DECLARACAO_FLAG_NAMES:
                if f"[{flag}]" in text:
                    leftovers.add(f"[{flag}]")
            for marker in SISGES_DOCUMENT_MARKER_MAP:
                if f"[[SISGES:{marker}]]" in text:
                    leftovers.add(f"[[SISGES:{marker}]]")
    return sorted(leftovers)


def _extract_xml_text(xml_bytes: bytes) -> str:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return xml_bytes.decode("utf-8", errors="ignore")
    return "".join(root.itertext())


def _content_xml(body_xml: str) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" office:version="1.2">
<office:automatic-styles>
<style:style style:name="Header" style:family="paragraph"><style:paragraph-properties fo:text-align="center"/><style:text-properties fo:font-weight="bold" fo:font-family="Calibri Light" fo:font-size="12pt"/></style:style>
<style:style style:name="Title" style:family="paragraph"><style:paragraph-properties fo:text-align="center" fo:margin-top="0.2in" fo:margin-bottom="0.2in"/><style:text-properties fo:font-weight="bold" fo:font-family="Calibri Light" fo:font-size="12pt"/></style:style>
<style:style style:name="Text" style:family="paragraph"><style:paragraph-properties fo:text-align="justify"/><style:text-properties fo:font-family="Calibri Light" fo:font-size="12pt"/></style:style>
<style:style style:name="Center" style:family="paragraph"><style:paragraph-properties fo:text-align="center"/><style:text-properties fo:font-family="Calibri Light" fo:font-size="12pt"/></style:style>
</office:automatic-styles>
<office:body><office:text>{body_xml}</office:text></office:body></office:document-content>'''


def _styles_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" office:version="1.2"><office:styles><style:default-style style:family="paragraph"><style:text-properties fo:font-family="Calibri Light" fo:font-size="12pt"/></style:default-style></office:styles></office:document-styles>'''


def _manifest_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8"?><manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2"><manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/><manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/><manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/><manifest:file-entry manifest:full-path="meta.xml" manifest:media-type="text/xml"/></manifest:manifest>'''


def _meta_xml() -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?><office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0" office:version="1.2"><office:meta><meta:generator>SISGES</meta:generator><meta:creation-date>{_now_iso()}</meta:creation-date></office:meta></office:document-meta>'''


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_zip(path: Path, entries: list[tuple[Path, str]]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for source, arcname in entries:
            package.write(source, arcname)


def _validation_text(validations: list[str], warnings: list[str], errors: list[str]) -> str:
    lines = [*validations, *warnings, *errors, "", "Validação gerada pelo Compilador documental SISGES."]
    return "\n".join(lines)


def _justification_text(document_type: str, variables: dict) -> str:
    return "\n".join(
        [
            f"Tipo documental: {document_type}",
            "Fonte principal: Gestão de Pessoal do SISGES.",
            f"Fonte de tempo: {(variables.get('tempo_servico') or {}).get('origem') or 'não aplicável'}",
            "Documento gerado com pacote auditável e snapshot variables.json.",
        ],
    )


def _manifest_payload(
    *,
    document_type: str,
    militar: MilitarModel,
    files: list[Path],
    validations: list[str],
    warnings: list[str],
    errors: list[str],
    package_mode: str,
) -> dict:
    return {
        "schema_version": "document-package-manifest-v1",
        "document_type": document_type,
        "package_mode": package_mode,
        "militar": {
            "id": militar.id,
            "nome_completo": militar.nome_completo,
            "identidade": militar.identidade,
        },
        "files": [{"filename": file.name, "sha256": sha256_file(file)} for file in files],
        "validations": validations,
        "warnings": warnings,
        "errors": errors,
        "generated_at": _now_iso(),
    }


def _today_pt() -> str:
    return datetime.now(UTC).strftime("%d/%m/%Y")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
