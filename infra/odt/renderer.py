from pathlib import Path
import re
import tempfile
import zipfile
from xml.sax.saxutils import escape


PLACEHOLDER_PATTERN = re.compile(r"\[[A-Z0-9_]+\]")
TEXT_P_PATTERN = re.compile(r"<text:p\b([^>]*)>(.*?)</text:p>", re.DOTALL)
TEXT_SPAN_PATTERN = re.compile(r"<text:span\b([^>]*)>(.*?)</text:span>", re.DOTALL)


def render_odt_from_template(
    template_path: str | Path,
    output_path: str | Path,
    placeholder_map: dict[str, str],
    part1_blocks: list[dict[str, str]] | None = None,
    nome_formatado_xml: str = "",
    bold_style_name: str = "Tbold",
) -> Path:
    template_path = Path(template_path)
    output_path = Path(output_path)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        extracted_dir = tmp_dir_path / "odt_extracted"
        extracted_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(template_path, "r") as zin:
            zin.extractall(extracted_dir)

        content_xml = extracted_dir / "content.xml"
        styles_xml = extracted_dir / "styles.xml"

        if not content_xml.exists():
            raise FileNotFoundError("content.xml não encontrado no template ODT.")

        content = content_xml.read_text(encoding="utf-8")
        styles = styles_xml.read_text(encoding="utf-8") if styles_xml.exists() else ""

        # 1) PARTE1 em content.xml
        if part1_blocks:
            content = replace_part1_placeholder_with_paragraphs(
                content,
                part1_blocks,
                bold_style_name=bold_style_name,
            )
        else:
            content = content.replace("[PARTE1]", "")

        # 2) NOME_FORMATADO em content.xml e styles.xml com fallback robusto
        if nome_formatado_xml:
            content, _ = replace_special_placeholder_anywhere(
                content,
                "[NOME_FORMATADO]",
                nome_formatado_xml,
            )

            if styles:
                styles, _ = replace_special_placeholder_anywhere(
                    styles,
                    "[NOME_FORMATADO]",
                    nome_formatado_xml,
                )
        else:
            content = content.replace("[NOME_FORMATADO]", "")
            if styles:
                styles = styles.replace("[NOME_FORMATADO]", "")

        # 3) Placeholders simples
        content = apply_placeholder_map(content, placeholder_map)
        if styles:
            styles = apply_placeholder_map(styles, placeholder_map)

        # 4) Limpeza preventiva
        content = content.replace("[NOME_FORMATADO]", "")
        if styles:
            styles = styles.replace("[NOME_FORMATADO]", "")

        # 5) Validação final
        validate_no_unresolved_placeholders(content, xml_name="content.xml")
        if styles:
            validate_no_unresolved_placeholders(styles, xml_name="styles.xml")

        content_xml.write_text(content, encoding="utf-8")
        if styles_xml.exists():
            styles_xml.write_text(styles, encoding="utf-8")

        with zipfile.ZipFile(output_path, "w") as zout:
            mimetype_path = extracted_dir / "mimetype"
            if mimetype_path.exists():
                zout.write(mimetype_path, "mimetype", compress_type=zipfile.ZIP_STORED)

            for file_path in sorted(extracted_dir.rglob("*")):
                if file_path.is_dir():
                    continue
                if file_path.name == "mimetype":
                    continue
                arcname = file_path.relative_to(extracted_dir)
                zout.write(file_path, str(arcname), compress_type=zipfile.ZIP_DEFLATED)

    return output_path


def apply_placeholder_map(xml_text: str, placeholder_map: dict[str, str]) -> str:
    result = xml_text

    for placeholder, value in sorted(
        placeholder_map.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        result = result.replace(placeholder, xml_escape_text(value))

    return result


def replace_special_placeholder_anywhere(
    xml_text: str,
    placeholder: str,
    rendered_inner_xml: str,
) -> tuple[str, bool]:
    """
    Tenta substituir placeholder especial em:
    1. <text:p>
    2. <text:span>
    3. substituição direta no XML
    """
    replaced, found = replace_inside_tag_pattern(
        xml_text,
        TEXT_P_PATTERN,
        "text:p",
        placeholder,
        rendered_inner_xml,
    )
    if found:
        return replaced, True

    replaced, found = replace_inside_tag_pattern(
        xml_text,
        TEXT_SPAN_PATTERN,
        "text:span",
        placeholder,
        rendered_inner_xml,
    )
    if found:
        return replaced, True

    if placeholder in xml_text:
        return xml_text.replace(placeholder, rendered_inner_xml, 1), True

    return xml_text, False


def replace_inside_tag_pattern(
    xml_text: str,
    pattern: re.Pattern[str],
    tag_name: str,
    placeholder: str,
    rendered_inner_xml: str,
) -> tuple[str, bool]:
    for match in pattern.finditer(xml_text):
        attrs = match.group(1) or ""
        inner_xml = match.group(2)

        if placeholder in inner_xml:
            new_inner = inner_xml.replace(placeholder, rendered_inner_xml, 1)
            original = match.group(0)
            replacement = f"<{tag_name}{attrs}>{new_inner}</{tag_name}>"
            return xml_text.replace(original, replacement, 1), True

    return xml_text, False


def replace_part1_placeholder_with_paragraphs(
    content_xml: str,
    part1_blocks: list[dict[str, str]],
    bold_style_name: str | None = None,
) -> str:
    match_found = None
    for match in TEXT_P_PATTERN.finditer(content_xml):
        inner_xml = match.group(2)
        if "[PARTE1]" in inner_xml:
            match_found = match
            break

    if not match_found:
        raise ValueError(
            "Placeholder [PARTE1] não encontrado em um parágrafo <text:p> do content.xml."
        )

    attrs = match_found.group(1) or ""
    original_paragraph = match_found.group(0)
    style_name = extract_style_name(attrs)

    rendered_paragraphs = []
    for block in part1_blocks:
        rendered_paragraphs.append(
            build_text_p_with_type(
                text=block["text"],
                block_type=block["type"],
                style_name=style_name,
                bold_style_name=bold_style_name,
            )
        )

    replacement = "".join(rendered_paragraphs)
    return content_xml.replace(original_paragraph, replacement, 1)


def extract_style_name(attrs: str) -> str | None:
    match = re.search(r'text:style-name="([^"]+)"', attrs)
    if match:
        return match.group(1)
    return None


def build_text_p_with_type(
    text: str,
    block_type: str,
    style_name: str | None = None,
    bold_style_name: str | None = None,
) -> str:
    style_attr = f' text:style-name="{style_name}"' if style_name else ""
    escaped_text = xml_escape_text(text)

    if block_type == "title" and bold_style_name:
        escaped_text = (
            f'<text:span text:style-name="{bold_style_name}">{escaped_text}</text:span>'
        )

    return f"<text:p{style_attr}>{escaped_text}</text:p>"


def xml_escape_text(value: str) -> str:
    return escape(value or "", entities={'"': "&quot;"})


def validate_no_unresolved_placeholders(xml_text: str, xml_name: str) -> None:
    leftovers = sorted(set(PLACEHOLDER_PATTERN.findall(xml_text)))
    if leftovers:
        raise ValueError(
            f"Placeholders não resolvidos em {xml_name}: {', '.join(leftovers)}"
        )