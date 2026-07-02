from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
import re
import zipfile
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET

from modules.compilador.application.folha_format_contract import (
    EMPTY_MONTH_BLOCK,
    EMPTY_MONTH_COMPACT_PLURAL,
    EMPTY_MONTH_COMPACT_SINGULAR,
    FolhaFormatContract,
    default_folha_format_contract,
    empty_month_text,
)
from modules.compilador.application.folha_models import (
    CompilerOptions,
    EventBlock,
    RenderResult,
    SicapexProfile,
    TableBlock,
)
from modules.compilador.application.odt_template_policy import (
    EXECUTABLE_TEMPLATE,
    SISGES_ASSINATURA_MARKER,
    SISGES_COMPORTAMENTO_MARKER,
    SISGES_FLAG_ASSINATURA_FUNCAO,
    SISGES_FLAG_ASSINATURA_NOME,
    SISGES_FLAG_COMPORTAMENTO,
    SISGES_FLAG_DATA_LOCAL,
    SISGES_FLAG_GRADUACAO,
    SISGES_FLAG_IDENTIDADE,
    SISGES_FLAG_NOME,
    SISGES_FLAG_PARTE_1,
    SISGES_FLAG_PERIODO,
    SISGES_FLAG_POSTO_GRADUACAO_CONTINUACAO,
    SISGES_FLAG_QMS,
    SISGES_FLAG_SEMESTRE_TEXTO,
    SISGES_HEADER_MARKER,
    SISGES_PRIMEIRA_PARTE_MARKER,
    SISGES_SEGUNDA_PARTE_MARKER,
    classify_odt_template,
    odt_has_sisges_marker_in_styles,
    validate_no_leftover_placeholders,
)
from modules.compilador.application.folha_xml_utils import (
    NOISE_FRAGMENTS,
    REFERENCE_PATTERN,
    cell_xml,
    classify_tipo_militar,
    clean_noise,
    days_inclusive,
    extract_regex,
    format_admin_days,
    format_calendar_ymd,
    format_identity,
    is_probable_title,
    nome_completo_xml,
    normalize_space,
    overlap_days,
    p,
    p_xml,
    parse_date_br,
    period_bounds,
    select_assinatura_for_options,
    semester_months,
    span,
    split_paragraphs,
    strip_accents,
    xml_attr,
)
from modules.compilador.application.folha_extraction import (
    extract_acrescimos,
    extract_comportamento,
    extract_data_praca,
    extract_events_from_bi_odt,
    extract_events_from_bi_pdf,
    extract_events_from_bi_source,
    extract_odt_table_rows,
    extract_pdf_text,
    extract_period_section,
    extract_qm,
    hydrate_profile_from_context,
    infer_grad_and_nome_guerra,
    normalize_qm,
    parse_sicapex_profile,
    read_odt_blocks,
)
from modules.compilador.application.folha_time_calc import (
    TimeSummary,
    calculate_times_from_context,
    calculate_times_from_sicapex,
    parse_iso_date,
    periodo_days_in_semester,
    periodo_days_total,
)
from modules.compilador.application.folha_event_validation import (
    build_justification,
    detect_sensitive_event,
    normalize_event_blocks,
    normalize_semester_events,
    qms_validation_lines,
    raw_qms_leaked,
    repair_fiscal_table,
    repair_tables_inside_event,
    sensitive_event_validations,
    split_embedded_events,
    validate_data_praca_against_events,
    validate_result,
    _legacy_normalize_qm,
    extract_function_term,
    is_recoverable_event_title,
    recover_missing_event_title,
)
from shared.utils.hashing import sha256_file
from shared.utils.qms import NormalizedQmResult, normalize_qas_qms_qm_for_header
from shared.utils.strings import slugify_filename


@dataclass(slots=True)
class FolhaCompilerResult:
    output_path: Path
    validation_path: Path
    justification_path: Path
    output_sha256: str
    slug: str
    profile: SicapexProfile
    times: TimeSummary
    events_count: int
    tables_count: int
    validation: list[str]
    justification: list[str]
    parte1_output_path: Path | None = None


class FolhaAlteracoesCompiler:
    def compile(
        self,
        *,
        bi_odt_path: str | Path,
        sicapex_pdf_path: str | Path | None = None,
        output_path: str | Path,
        options: CompilerOptions | None = None,
        template_odt_path: str | Path | None = None,
        sicapex_context: dict | None = None,
    ) -> FolhaCompilerResult:
        options = options or CompilerOptions()
        bi_odt_path = Path(bi_odt_path)
        sicapex_pdf_path = Path(sicapex_pdf_path) if sicapex_pdf_path else None
        output_path = Path(output_path)

        sicapex_text = extract_pdf_text(sicapex_pdf_path) if sicapex_pdf_path else ""
        profile = parse_sicapex_profile(sicapex_text) if sicapex_text else SicapexProfile()
        if sicapex_context:
            profile = hydrate_profile_from_context(profile, sicapex_context)
        period_start, period_end, period_label = period_bounds(options.ano, options.semestre)
        events, odt_tables_detected = extract_events_from_bi_source(bi_odt_path, options)
        events, period_validations = normalize_semester_events(events, options.semestre, options.ano)
        events, event_validations = normalize_event_blocks(events)
        event_validations = [*period_validations, *event_validations]
        event_validations.extend(validate_data_praca_against_events(profile, events))
        sensitive_validations = sensitive_event_validations(events)
        times = calculate_times_from_sicapex(profile, period_start, period_end)
        if sicapex_context:
            times = calculate_times_from_context(
                sicapex_context,
                period_start,
                period_end,
                fallback=times,
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        qms_result = normalize_qas_qms_qm_for_header(profile.qm)
        profile.qm = qms_result.display
        render_result = render_final_odt(
            output_path=output_path,
            profile=profile,
            events=events,
            times=times,
            period_label=period_label,
            options=options,
            template_odt_path=Path(template_odt_path) if template_odt_path else None,
        )
        parte1_output_path = output_path.with_name("parte_1_alteracoes.odt")
        parte1_validations = render_primeira_parte_odt(
            output_path=parte1_output_path,
            events=events,
            options=options,
        )

        validation = validate_result(
            output_path,
            profile,
            events,
            times,
            options,
            render_result=render_result,
            qms_result=qms_result,
        )
        validation.extend(event_validations)
        validation.extend(sensitive_validations)
        validation.extend(parte1_validations)
        justification = build_justification(
            profile=profile,
            events=events,
            times=times,
            options=options,
            odt_tables_detected=odt_tables_detected,
            period_label=period_label,
        )
        if sicapex_context:
            source = sicapex_context.get("fonte_sicapex") or {}
            validation.append("Fonte de tempo: banco SISGES alimentado por Ficha SiCaPEx.")
            validation.append("Calculo automatizado pendente de validacao humana.")
            justification.append(
                "Fonte de tempo: banco SISGES alimentado por Ficha SiCaPEx, "
                f"arquivo {source.get('filename') or '-'}, SHA {source.get('sha256') or '-'}."
            )
            justification.append("Calculo automatizado pendente de validacao humana.")

        validation_path = output_path.with_suffix(".validacao.txt")
        justification_path = output_path.with_suffix(".justificativa.txt")
        validation_path.write_text("\n".join(validation) + "\n", encoding="utf-8")
        justification_path.write_text("\n".join(justification) + "\n", encoding="utf-8")

        return FolhaCompilerResult(
            output_path=output_path,
            validation_path=validation_path,
            justification_path=justification_path,
            output_sha256=sha256_file(output_path),
            slug=slugify_filename(profile.nome_completo or "folha-alteracoes"),
            profile=profile,
            times=times,
            events_count=len(events),
            tables_count=sum(len(event.tables) for event in events),
            validation=validation,
            justification=justification,
            parte1_output_path=parte1_output_path,
        )


def render_final_odt(
    *,
    output_path: Path,
    profile: SicapexProfile,
    events: list[EventBlock],
    times: TimeSummary,
    period_label: str,
    options: CompilerOptions,
    template_odt_path: Path | None = None,
) -> RenderResult:
    profile.qm = normalize_qas_qms_qm_for_header(profile.qm).display
    body_xml = build_body_xml(profile, events, times, period_label, options)
    if template_odt_path:
        return render_folha_from_template(
            template_odt_path=template_odt_path,
            output_odt_path=output_path,
            body_xml=body_xml,
            profile=profile,
            events=events,
            times=times,
            period_label=period_label,
            options=options,
        )

    return render_internal_odt(output_path=output_path, body_xml=body_xml, options=options)


def render_primeira_parte_odt(
    *,
    output_path: Path,
    events: list[EventBlock],
    options: CompilerOptions,
) -> list[str]:
    body_xml = first_part_xml(events, options)
    result = render_internal_odt(
        output_path=output_path,
        body_xml=body_xml,
        options=options,
        template_provided=True,
    )
    return list(
        dict.fromkeys(
            [
                "OK_PARTE1_ODT_GENERATED",
                "OK_FORMAT_CONTRACT_APPLIED",
                *result.validations,
            ]
        )
    )


def render_internal_odt(
    *,
    output_path: Path,
    body_xml: str,
    options: CompilerOptions,
    extra_validations: list[str] | None = None,
    template_provided: bool = False,
) -> RenderResult:
    content_xml = build_content_xml(body_xml, options)
    styles_xml = build_styles_xml(options)
    manifest_xml = build_manifest_xml()
    meta_xml = """<?xml version=\"1.0\" encoding=\"UTF-8\"?><office:document-meta xmlns:office=\"urn:oasis:names:tc:opendocument:xmlns:office:1.0\" office:version=\"1.2\"><office:meta/></office:document-meta>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w") as zout:
        zout.writestr("mimetype", "application/vnd.oasis.opendocument.text", compress_type=zipfile.ZIP_STORED)
        zout.writestr("content.xml", content_xml, compress_type=zipfile.ZIP_DEFLATED)
        zout.writestr("styles.xml", styles_xml, compress_type=zipfile.ZIP_DEFLATED)
        zout.writestr("meta.xml", meta_xml, compress_type=zipfile.ZIP_DEFLATED)
        zout.writestr("META-INF/manifest.xml", manifest_xml, compress_type=zipfile.ZIP_DEFLATED)
    validations = ["OK_ODT_ZIP_VALID", "OK_CONTENT_XML_VALID"]
    if not template_provided:
        validations.append("WARN_TEMPLATE_NOT_PROVIDED")
    validations.extend(validate_no_leftover_placeholders(content_xml, styles_xml))
    if extra_validations:
        validations.extend(extra_validations)
    return RenderResult(validations=list(dict.fromkeys(validations)))


def render_folha_from_template(
    *,
    template_odt_path: Path,
    output_odt_path: Path,
    body_xml: str,
    profile: SicapexProfile,
    events: list[EventBlock],
    times: TimeSummary,
    period_label: str,
    options: CompilerOptions,
) -> RenderResult:
    if not template_odt_path.exists():
        raise FileNotFoundError(f"ERR_TEMPLATE_NOT_FOUND:{template_odt_path}")
    classification = classify_odt_template(template_odt_path)
    if classification.classification != EXECUTABLE_TEMPLATE:
        if "ERR_TEMPLATE_ODT_INVALID" in classification.validations:
            raise ValueError("ERR_TEMPLATE_ODT_INVALID")
        fallback = render_internal_odt(
            output_path=output_odt_path,
            body_xml=body_xml,
            options=options,
            extra_validations=classification.validations,
            template_provided=True,
        )
        fallback.template_provided = True
        fallback.template_used = False
        fallback.template_sha256 = sha256_file(template_odt_path)
        fallback.strategy = "internal_fallback"
        fallback.warnings.extend(classification.validations)
        return fallback
    if odt_has_sisges_marker_in_styles(classification.styles_xml):
        fallback = render_internal_odt(
            output_path=output_odt_path,
            body_xml=body_xml,
            options=options,
            extra_validations=["ERR_TEMPLATE_HEADER_MARKERS_UNSUPPORTED"],
            template_provided=True,
        )
        fallback.template_provided = True
        fallback.template_used = False
        fallback.template_sha256 = sha256_file(template_odt_path)
        fallback.strategy = "internal_fallback"
        fallback.warnings.append("ERR_TEMPLATE_HEADER_MARKERS_UNSUPPORTED")
        return fallback
    with zipfile.ZipFile(template_odt_path, "r") as zin:
        entries = {info.filename: zin.read(info.filename) for info in zin.infolist() if not info.is_dir()}
    if "content.xml" not in entries:
        raise ValueError("ERR_TEMPLATE_CONTENT_NOT_FOUND")

    content_xml = entries["content.xml"].decode("utf-8")
    styles_xml = entries.get("styles.xml", b"").decode("utf-8")
    content_xml, styles_xml, strategy = inject_template_parts(
        content_xml,
        styles_xml,
        body_xml,
        profile,
        events,
        times,
        period_label,
        options,
    )
    entries["content.xml"] = content_xml.encode("utf-8")
    if "styles.xml" in entries:
        entries["styles.xml"] = styles_xml.encode("utf-8")

    output_odt_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_odt_path, "w") as zout:
        if "mimetype" in entries:
            zout.writestr("mimetype", entries.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
        else:
            zout.writestr("mimetype", "application/vnd.oasis.opendocument.text", compress_type=zipfile.ZIP_STORED)
        for filename, data in entries.items():
            zout.writestr(filename, data, compress_type=zipfile.ZIP_DEFLATED)

    validations = validate_odt_format(output_odt_path, template_odt_path=template_odt_path)
    validations.append("OK_TEMPLATE_USED")
    validations.extend(classification.validations)
    return RenderResult(
        template_provided=True,
        template_used=True,
        template_sha256=sha256_file(template_odt_path),
        strategy=strategy,
        validations=list(dict.fromkeys(validations)),
    )


def inject_template_parts(
    content_xml: str,
    styles_xml: str,
    body_xml: str,
    profile: SicapexProfile,
    events: list[EventBlock],
    times: TimeSummary,
    period_label: str,
    options: CompilerOptions,
) -> tuple[str, str, str]:
    flag_values = sisges_flag_values(profile, events, times, period_label, options)
    combined = f"{content_xml}\n{styles_xml}"
    if any(token in combined for token in flag_values):
        content_xml = replace_paragraph_marker_with_xml(
            content_xml,
            SISGES_FLAG_PARTE_1,
            first_part_months_xml(events, options),
        )
        for token, value in flag_values.items():
            content_xml = content_xml.replace(token, value)
            styles_xml = styles_xml.replace(token, value)
        return content_xml, styles_xml, "sisges-flags"
    content_xml, strategy = inject_template_content(
        content_xml,
        body_xml,
        profile,
        events,
        times,
        period_label,
        options,
    )
    return content_xml, styles_xml, strategy


def inject_template_content(
    content_xml: str,
    body_xml: str,
    profile: SicapexProfile,
    events: list[EventBlock],
    times: TimeSummary,
    period_label: str,
    options: CompilerOptions,
) -> tuple[str, str]:
    sisges_values = sisges_marker_values(profile, events, times, period_label, options)
    if any(token in content_xml for token in sisges_values):
        for token, value in sisges_values.items():
            content_xml = content_xml.replace(token, value)
        for token, value in template_placeholder_values(profile, events, times, period_label, options).items():
            content_xml = content_xml.replace(token, value)
        return content_xml, "sisges-marker"
    placeholders = template_placeholder_values(profile, events, times, period_label, options)
    if any(token in content_xml for token in placeholders):
        for token, value in placeholders.items():
            content_xml = content_xml.replace(token, value)
        return content_xml, "placeholder"
    if has_template_anchors(content_xml):
        return replace_office_text_body(content_xml, body_xml), "anchor"
    raise ValueError("ERR_TEMPLATE_ANCHOR_NOT_FOUND")


def replace_paragraph_marker_with_xml(content_xml: str, token: str, replacement_xml: str) -> str:
    index = content_xml.find(token)
    if index < 0:
        return content_xml
    start = content_xml.rfind("<text:p", 0, index)
    end = content_xml.find("</text:p>", index)
    if start < 0 or end < 0:
        return content_xml.replace(token, replacement_xml)
    return content_xml[:start] + replacement_xml + content_xml[end + len("</text:p>") :]


def sisges_flag_values(
    profile: SicapexProfile,
    events: list[EventBlock],
    times: TimeSummary,
    period_label: str,
    options: CompilerOptions,
) -> dict[str, str]:
    _ = (events, times)
    assinatura_nome, assinatura_funcao = select_assinatura_for_options(profile, options)
    graduacao = profile.graduacao_extenso or profile.graduacao_abrev
    return {
        SISGES_FLAG_NOME: escape(profile.nome_completo),
        SISGES_FLAG_GRADUACAO: escape(graduacao),
        SISGES_FLAG_QMS: escape(profile.qm),
        SISGES_FLAG_IDENTIDADE: escape(profile.identidade),
        SISGES_FLAG_SEMESTRE_TEXTO: escape(period_label),
        SISGES_FLAG_PERIODO: escape(periodo_curto(options)),
        SISGES_FLAG_POSTO_GRADUACAO_CONTINUACAO: escape(graduacao.upper() if graduacao else ""),
        SISGES_FLAG_COMPORTAMENTO: comportamento_text(profile),
        SISGES_FLAG_DATA_LOCAL: "Quartel-General do Exército – Brasília/DF, 1° de janeiro de 2026",
        SISGES_FLAG_ASSINATURA_NOME: escape(assinatura_nome),
        SISGES_FLAG_ASSINATURA_FUNCAO: escape(assinatura_funcao),
    }


def periodo_curto(options: CompilerOptions) -> str:
    return "1º JAN A 30 JUN" if str(options.semestre).strip().startswith("1") else "1º JUL A 31 DEZ"


def comportamento_text(profile: SicapexProfile) -> str:
    if not profile.comportamento:
        return ""
    return f"Comportamento: {profile.comportamento.upper()}"


def sisges_marker_values(
    profile: SicapexProfile,
    events: list[EventBlock],
    times: TimeSummary,
    period_label: str,
    options: CompilerOptions,
) -> dict[str, str]:
    assinatura_nome, assinatura_funcao = select_assinatura_for_options(profile, options)
    return {
        SISGES_HEADER_MARKER: header_xml(profile, period_label, options),
        SISGES_PRIMEIRA_PARTE_MARKER: first_part_xml(events, options),
        SISGES_COMPORTAMENTO_MARKER: comportamento_xml(profile),
        SISGES_SEGUNDA_PARTE_MARKER: second_part_xml(profile, times),
        SISGES_ASSINATURA_MARKER: assinatura_xml(assinatura_nome, assinatura_funcao),
    }


def header_xml(profile: SicapexProfile, period_label: str, options: CompilerOptions) -> str:
    return "".join(
        [
            p("MINISTÉRIO DA DEFESA", "Header"),
            p("EXÉRCITO BRASILEIRO", "Header"),
            p("B ADM QGEX - 001156", "Header"),
            p_xml("NOME: " + nome_completo_xml(profile.nome_completo, profile.nome_guerra), "Standard"),
            p(f"GRADUAÇÃO: {profile.graduacao_extenso or profile.graduacao_abrev}", "Standard"),
            p(f"ARMA/QUADRO/SERVIÇO: {profile.qm}", "Standard"),
            p(f"IDENTIDADE: {profile.identidade}", "Standard"),
            p("FOLHAS DE ALTERAÇÕES", "Title"),
            p("GUARNIÇÃO DE BRASÍLIA", "Header"),
            p(period_label, "Header"),
            p("PERÍODO: 1º JUL A 31 DEZ" if options.semestre == "2" else "PERÍODO: 1º JAN A 30 JUN", "Header"),
        ]
    )


def assinatura_xml(assinatura_nome: str, assinatura_funcao: str) -> str:
    return "".join(
        [
            p("Quartel-General do Exército - Brasília/DF, 1º de janeiro de 2026", "Center"),
            p("", "Center"),
            p("", "Center"),
            p(assinatura_nome, "Center"),
            p(assinatura_funcao, "Center"),
        ]
    )


def template_placeholder_values(
    profile: SicapexProfile,
    events: list[EventBlock],
    times: TimeSummary,
    period_label: str,
    options: CompilerOptions,
) -> dict[str, str]:
    assinatura_nome, assinatura_funcao = select_assinatura_for_options(profile, options)
    primeira = first_part_xml(events, options)
    segunda = second_part_xml(profile, times)
    return {
        "{{NOME_COMPLETO}}": escape(profile.nome_completo),
        "{{NOME_COMPLETO_COM_GUERRA_BOLD}}": nome_completo_xml(profile.nome_completo, profile.nome_guerra),
        "{{POSTO_GRADUACAO}}": escape(profile.graduacao_extenso or profile.graduacao_abrev),
        "{{QAS_QMS_QM}}": escape(profile.qm),
        "{{IDENTIDADE}}": escape(profile.identidade),
        "{{PERIODO}}": escape(period_label),
        "{{PRIMEIRA_PARTE}}": primeira,
        "{{COMPORTAMENTO}}": comportamento_xml(profile),
        "{{SEGUNDA_PARTE}}": segunda,
        "{{ASSINATURA_NOME}}": escape(assinatura_nome),
        "{{ASSINATURA_FUNCAO}}": escape(assinatura_funcao),
        "{{DATA_LOCAL}}": "Quartel-General do Exército – Brasília/DF, 1º de janeiro de 2026",
    }


def has_template_anchors(content_xml: str) -> bool:
    plain = re.sub(r"<[^>]+>", " ", content_xml)
    comparable = strip_accents(normalize_space(plain)).upper()
    return "1A PARTE" in comparable and "2A PARTE" in comparable


def replace_office_text_body(content_xml: str, body_xml: str) -> str:
    match = re.search(r"(<office:text[^>]*>)(.*?)(</office:text>)", content_xml, flags=re.S)
    if not match:
        raise ValueError("ERR_TEMPLATE_ANCHOR_NOT_FOUND")
    return content_xml[: match.start(2)] + body_xml + content_xml[match.end(2) :]


def validate_odt_format(output_odt_path: Path, template_odt_path: Path | None = None) -> list[str]:
    validations: list[str] = []
    try:
        with zipfile.ZipFile(output_odt_path, "r") as zout:
            content = zout.read("content.xml")
            styles = zout.read("styles.xml")
        validations.append("OK_ODT_ZIP_VALID")
        ET.fromstring(content)
        validations.append("OK_CONTENT_XML_VALID")
        ET.fromstring(styles)
        validations.append("OK_STYLES_XML_VALID")
    except Exception:
        return ["ERR_CONTENT_XML_INVALID"]
    text = content.decode("utf-8", errors="ignore")
    styles_text = styles.decode("utf-8", errors="ignore")
    validations.extend(validate_no_leftover_placeholders(text, styles_text))
    if template_odt_path:
        with zipfile.ZipFile(template_odt_path, "r") as tin:
            template_styles = tin.read("styles.xml") if "styles.xml" in tin.namelist() else b""
        template_styles_text = template_styles.decode("utf-8", errors="ignore")
        if template_styles and styles == template_styles:
            validations.append("OK_STYLES_PRESERVED")
        elif "[SISGES_" in template_styles_text and "[SISGES_" not in styles_text:
            validations.append("OK_STYLES_PRESERVED")
            validations.append("OK_HEADER_STYLES_RENDERED")
        else:
            validations.append("ERR_STYLES_NOT_PRESERVED")
    if "Calibri Light" in text or b"Calibri Light" in styles:
        validations.append("OK_MAIN_FONT")
    else:
        validations.append("WARN_FONT_NOT_CONFIRMED")
    if "text-align=\"center\"" in text or "fo:text-align=\"center\"" in text:
        validations.append("OK_SIGNATURE_CENTERED")
    else:
        validations.append("WARN_SIGNATURE_ALIGNMENT_NOT_CONFIRMED")
    return validations


def append_month_heading(lines: list[str], month: str, has_events: bool, contract: FolhaFormatContract) -> None:
    mode = contract.normalized_empty_month_mode()
    if has_events or mode == EMPTY_MONTH_BLOCK:
        lines.append(p(month + ":", contract.month_style))


def append_empty_month(lines: list[str], month: str, contract: FolhaFormatContract) -> None:
    mode = contract.normalized_empty_month_mode()
    if mode in {EMPTY_MONTH_COMPACT_SINGULAR, EMPTY_MONTH_COMPACT_PLURAL}:
        lines.append(p(empty_month_text(month, mode), contract.month_style))
    else:
        lines.append(p(empty_month_text(month, mode), contract.body_style))


def build_body_xml(
    profile: SicapexProfile,
    events: list[EventBlock],
    times: TimeSummary,
    period_label: str,
    options: CompilerOptions,
) -> str:
    contract = default_folha_format_contract(empty_month_mode=options.empty_month_mode)
    assinatura_nome, assinatura_funcao = select_assinatura_for_options(profile, options)
    lines: list[str] = []

    lines.append(p("MINISTÉRIO DA DEFESA", "Header"))
    lines.append(p("EXÉRCITO BRASILEIRO", "Header"))
    lines.append(p("B ADM QGEX – 001156", "Header"))
    lines.append(p_xml("NOME: " + nome_completo_xml(profile.nome_completo, profile.nome_guerra), "Standard"))
    lines.append(p(f"GRADUAÇÃO: {profile.graduacao_extenso or profile.graduacao_abrev}", "Standard"))
    lines.append(p(f"ARMA/QUADRO/SERVIÇO: {profile.qm}", "Standard"))
    lines.append(p(f"IDENTIDADE: {profile.identidade}", "Standard"))
    lines.append(p("FOLHAS DE ALTERAÇÕES", "Title"))
    lines.append(p("GUARNIÇÃO DE BRASÍLIA", "Header"))
    lines.append(p(period_label, "Header"))
    lines.append(p("PERÍODO: 1º JUL A 31 DEZ" if options.semestre == "2" else "PERÍODO: 1º JAN A 30 JUN", "Header"))
    lines.append(p("1ª PARTE", "Title"))

    by_month: dict[str, list[EventBlock]] = {month: [] for month in semester_months(options.semestre)}
    for event in events:
        if event.mes in by_month:
            by_month[event.mes].append(event)

    for month in semester_months(options.semestre):
        append_month_heading(lines, month, bool(by_month[month]), contract)
        if not by_month[month]:
            append_empty_month(lines, month, contract)
            continue
        for event in by_month[month]:
            if event.titulo:
                lines.append(p_xml(span(event.titulo, "Bold"), "Standard"))
            if event.referencia:
                lines.append(p(event.referencia, "Standard"))
            for paragraph in split_paragraphs(event.corpo):
                lines.append(p(paragraph, "Standard"))
            for table in event.tables:
                lines.append(table_xml(table))
            lines.append(p("", "Standard"))

    if profile.comportamento:
        lines.append(p_xml("COMPORTAMENTO: " + span(profile.comportamento.upper(), "Bold"), "Standard"))

    lines.append(p("2ª PARTE", "Title"))
    lines.append(times_table_xml(times))
    lines.append(p("Quartel-General do Exército – Brasília/DF, 1º de janeiro de 2026", "Center"))
    lines.append(p("", "Center"))
    lines.append(p("", "Center"))
    lines.append(p(assinatura_nome, "Center"))
    lines.append(p(assinatura_funcao, "Center"))
    return "".join(lines)


def first_part_xml(events: list[EventBlock], options: CompilerOptions) -> str:
    return p("1ª PARTE", "Title") + first_part_months_xml(events, options)


def first_part_months_xml(events: list[EventBlock], options: CompilerOptions) -> str:
    contract = default_folha_format_contract(empty_month_mode=options.empty_month_mode)
    lines: list[str] = []
    by_month: dict[str, list[EventBlock]] = {month: [] for month in semester_months(options.semestre)}
    for event in events:
        if event.mes in by_month:
            by_month[event.mes].append(event)
    for month in semester_months(options.semestre):
        append_month_heading(lines, month, bool(by_month[month]), contract)
        if not by_month[month]:
            append_empty_month(lines, month, contract)
            continue
        for event in by_month[month]:
            if event.titulo:
                lines.append(p_xml(span(event.titulo, "Bold"), "Standard"))
            if event.referencia:
                lines.append(p(event.referencia, "Standard"))
            for paragraph in split_paragraphs(event.corpo):
                lines.append(p(paragraph, "Standard"))
            for table in event.tables:
                lines.append(table_xml(table))
            lines.append(p("", "Standard"))
    return "".join(lines)


def second_part_xml(profile: SicapexProfile, times: TimeSummary) -> str:
    lines = []
    if profile.comportamento:
        lines.append(comportamento_xml(profile))
    lines.append(p("2ª PARTE", "Title"))
    lines.append(times_table_xml(times))
    return "".join(lines)


def comportamento_xml(profile: SicapexProfile) -> str:
    if not profile.comportamento:
        return ""
    return p_xml("COMPORTAMENTO: " + span(profile.comportamento.upper(), "Bold"), "Standard")


def table_xml(table: TableBlock) -> str:
    columns = table.columns or ["Designado", "Função", "Área de responsabilidade"]
    rows = table.rows or []
    xml = [f'<table:table table:name="{xml_attr(table.title or "Tabela")}">']
    for _ in columns:
        xml.append('<table:table-column table:style-name="Col"/>')
    xml.append("<table:table-row>")
    for column in columns:
        xml.append(cell_xml(column, bold=True))
    xml.append("</table:table-row>")
    for row in rows:
        xml.append("<table:table-row>")
        normalized_row = list(row)[: len(columns)]
        while len(normalized_row) < len(columns):
            normalized_row.append("")
        for value in normalized_row:
            xml.append(cell_xml(value, bold=False))
        xml.append("</table:table-row>")
    xml.append("</table:table>")
    return "".join(xml)


def times_table_xml(times: TimeSummary) -> str:
    # Ordem dos títulos fixada pelo Art. 24 da Port. 063-DGP/2020 (Anexo B):
    # I-TC, II-TNC, III-TSSD, IV-TSCMM, V-TSNR, VI-TTES.
    rows = [
        ("1. TEMPO COMPUTADO DE EFETIVO SERVIÇO (TC)", times.tc),
        ("a) Arregimentado", times.tc_arreg),
        ("b) Não arregimentado", times.tc_nao_arreg),
        ("c) Trânsito", times.tc_transito),
        ("d) Instalação", times.tc_instalacao),
        ("2. TEMPO NÃO COMPUTADO (TNC)", times.tnc),
        ("3. TEMPO DE SERVIÇO EM SITUAÇÕES DIVERSAS (TSSD)", times.tssd),
        ("4. TEMPO DE SERVIÇO COMPUTADO PARA MEDALHA MILITAR (TSCMM)", times.tscmm),
        ("5. TEMPO DE SERVIÇO NACIONAL RELEVANTE (TSNR)", times.tsnr),
        ("6. TEMPO TOTAL DE EFETIVO SERVIÇO (TTES)", times.ttes),
    ]
    return table_xml(TableBlock(title="2ª PARTE", columns=["Rubrica", "Tempo"], rows=[list(row) for row in rows]))

def build_content_xml(body_xml: str, options: CompilerOptions) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" office:version="1.2">
<office:automatic-styles>
<style:style style:name="Standard" style:family="paragraph"><style:text-properties fo:font-family="{escape(options.fonte)}" fo:font-size="{options.tamanho_fonte}pt"/></style:style>
<style:style style:name="Header" style:family="paragraph"><style:text-properties fo:font-family="{escape(options.fonte)}" fo:font-size="{options.tamanho_fonte}pt"/></style:style>
<style:style style:name="Title" style:family="paragraph"><style:text-properties fo:font-family="{escape(options.fonte)}" fo:font-size="{options.tamanho_fonte}pt" fo:font-weight="bold"/></style:style>
<style:style style:name="Month" style:family="paragraph"><style:text-properties fo:font-family="{escape(options.fonte)}" fo:font-size="{options.tamanho_fonte}pt" style:text-underline-style="solid"/></style:style>
<style:style style:name="Center" style:family="paragraph"><style:paragraph-properties fo:text-align="center"/><style:text-properties fo:font-family="{escape(options.fonte)}" fo:font-size="{options.tamanho_fonte}pt"/></style:style>
<style:style style:name="Bold" style:family="text"><style:text-properties fo:font-weight="bold"/></style:style>
<style:style style:name="Cell" style:family="table-cell"><style:table-cell-properties fo:border="0.5pt solid #000000" fo:padding="0.05in"/></style:style>
<style:style style:name="Col" style:family="table-column"><style:table-column-properties style:column-width="2.2in"/></style:style>
</office:automatic-styles>
<office:body><office:text>{body_xml}</office:text></office:body></office:document-content>'''


def build_styles_xml(options: CompilerOptions) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" office:version="1.2"><office:styles><style:default-style style:family="paragraph"><style:text-properties fo:font-family="{escape(options.fonte)}" fo:font-size="{options.tamanho_fonte}pt"/></style:default-style></office:styles></office:document-styles>'''


def build_manifest_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2"><manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/><manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/><manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/><manifest:file-entry manifest:full-path="meta.xml" manifest:media-type="text/xml"/></manifest:manifest>'''



