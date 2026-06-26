from pathlib import Path

from modules.compilador.domain.entities import CompilationRecord
from infra.odt.template_mapper import (
    build_placeholder_map,
    build_part1_blocks,
    build_nome_formatado_xml,
)
from infra.odt.renderer import render_odt_from_template


class RenderOdtUseCase:
    def execute(
        self,
        record: CompilationRecord,
        template_path: str | Path,
        output_path: str | Path,
    ) -> dict:
        if record.pending_fields:
            raise ValueError(
                "Existem pendências canônicas. A finalização está bloqueada."
            )

        placeholder_map = build_placeholder_map(record)
        part1_blocks = build_part1_blocks(record)
        nome_formatado_xml = build_nome_formatado_xml(
            nome_completo=record.header.nome_completo,
            nome_guerra=record.header.nome_guerra,
            bold_style_name="Tbold",
        )

        generated_path = render_odt_from_template(
            template_path=template_path,
            output_path=output_path,
            placeholder_map=placeholder_map,
            part1_blocks=part1_blocks,
            nome_formatado_xml=nome_formatado_xml,
            bold_style_name="Tbold",
        )

        return {
            "output_path": str(generated_path),
            "placeholders_used": sorted(list(placeholder_map.keys())),
            "part1_blocks_count": len(part1_blocks),
            "nome_formatado_aplicado": bool(nome_formatado_xml),
        }