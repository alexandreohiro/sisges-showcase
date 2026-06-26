from modules.compilador.domain.entities import CompilationRecord


def validate_record(record: CompilationRecord) -> list[str]:
    diagnostics: list[str] = []

    if not record.header.nome_completo:
        diagnostics.append("MISSING_HEADER_NOME")
    if not record.header.graduacao:
        diagnostics.append("MISSING_HEADER_GRADUACAO")
    if not record.header.identidade:
        diagnostics.append("MISSING_HEADER_IDENTIDADE")

    if not record.part1:
        diagnostics.append("MISSING_PART1")

    if not record.part2.tc:
        diagnostics.append("MISSING_PART2_TC")
    if not record.part2.tscmm:
        diagnostics.append("MISSING_PART2_TSCMM")
    if not record.part2.ttes:
        diagnostics.append("MISSING_PART2_TTES")

    for pending in record.pending_fields:
        diagnostics.append(f"PENDING_FIELD:{pending.field_name}:{pending.reason}")

    return diagnostics