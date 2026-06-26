from __future__ import annotations

from pathlib import Path
import zipfile

from modules.compilador.application.folha_format_contract import (
    FolhaFormatContract,
    default_folha_format_contract,
)
from modules.compilador.application.odt_template_policy import (
    SISGES_ASSINATURA_MARKER,
    SISGES_COMPORTAMENTO_MARKER,
    SISGES_HEADER_MARKER,
    SISGES_PRIMEIRA_PARTE_MARKER,
    SISGES_SEGUNDA_PARTE_MARKER,
)


DEFAULT_TEMPLATE_NAME = "sisges_folha_alteracoes_default_template.odt"


def ensure_default_folha_template(
    output_dir: Path | None = None,
    *,
    contract: FolhaFormatContract | None = None,
) -> Path:
    """Cria um modelo ODT interno minimo, valido e executavel pelo SISGES."""
    contract = contract or default_folha_format_contract()
    target_dir = output_dir or Path("data/compiler_memory/internal_templates")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / DEFAULT_TEMPLATE_NAME
    if target.exists():
        target.unlink()

    meta_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'office:version="1.2"><office:meta/></office:document-meta>'
    )
    with zipfile.ZipFile(target, "w") as zout:
        zout.writestr("mimetype", "application/vnd.oasis.opendocument.text", compress_type=zipfile.ZIP_STORED)
        zout.writestr("content.xml", _content_xml(), compress_type=zipfile.ZIP_DEFLATED)
        zout.writestr("styles.xml", _styles_xml(contract), compress_type=zipfile.ZIP_DEFLATED)
        zout.writestr("meta.xml", meta_xml, compress_type=zipfile.ZIP_DEFLATED)
        zout.writestr("META-INF/manifest.xml", _manifest_xml(), compress_type=zipfile.ZIP_DEFLATED)
    return target


def _content_xml() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
  xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
  xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
  xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
  office:version="1.2">
  <office:automatic-styles>
    <style:style style:name="P1" style:family="paragraph"/>
  </office:automatic-styles>
  <office:body>
    <office:text>
      <text:variable-decls>
        <text:variable-decl text:name="{{{{NOME_COMPLETO_COM_GUERRA_BOLD}}}}" office:value-type="string"/>
        <text:variable-decl text:name="{{{{POSTO_GRADUACAO}}}}" office:value-type="string"/>
        <text:variable-decl text:name="{{{{QAS_QMS_QM}}}}" office:value-type="string"/>
        <text:variable-decl text:name="{{{{IDENTIDADE}}}}" office:value-type="string"/>
        <text:variable-decl text:name="{{{{PERIODO}}}}" office:value-type="string"/>
        <text:variable-decl text:name="{{{{ASSINATURA_NOME}}}}" office:value-type="string"/>
        <text:variable-decl text:name="{{{{ASSINATURA_FUNCAO}}}}" office:value-type="string"/>
      </text:variable-decls>
      {SISGES_HEADER_MARKER}
      {SISGES_PRIMEIRA_PARTE_MARKER}
      {SISGES_COMPORTAMENTO_MARKER}
      {SISGES_SEGUNDA_PARTE_MARKER}
      {SISGES_ASSINATURA_MARKER}
    </office:text>
  </office:body>
</office:document-content>
"""


def _styles_xml(contract: FolhaFormatContract) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles
  xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
  xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
  office:version="1.2">
  <office:styles>
    <style:default-style style:family="paragraph">
      <style:text-properties fo:font-size="{contract.font_size}pt" style:font-name="{contract.font_family}"/>
    </style:default-style>
    <style:style style:name="Standard" style:family="paragraph">
      <style:text-properties fo:font-size="{contract.font_size}pt" style:font-name="{contract.font_family}"/>
    </style:style>
  </office:styles>
</office:document-styles>
"""


def _manifest_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest
  xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
  manifest:version="1.2">
  <manifest:file-entry manifest:media-type="application/vnd.oasis.opendocument.text" manifest:full-path="/"/>
  <manifest:file-entry manifest:media-type="text/xml" manifest:full-path="content.xml"/>
  <manifest:file-entry manifest:media-type="text/xml" manifest:full-path="styles.xml"/>
  <manifest:file-entry manifest:media-type="text/xml" manifest:full-path="meta.xml"/>
</manifest:manifest>
"""
