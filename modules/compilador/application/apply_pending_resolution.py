from modules.compilador.domain.entities import CompilationRecord


class ApplyPendingResolutionUseCase:
    def execute(
        self,
        record: CompilationRecord,
        resolutions: dict,
    ) -> CompilationRecord:
        resolved_fields = set()

        for field_name, payload in resolutions.items():
            value = (payload or {}).get("value", "")
            if not value:
                continue

            if field_name == "nome_guerra":
                record.header.nome_guerra = value.strip()
                resolved_fields.add("nome_guerra")

            elif field_name == "qm":
                record.header.qm = value.strip()
                resolved_fields.add("qm")

            elif field_name == "data_de_praca":
                record.header.data_de_praca = value.strip()
                resolved_fields.add("data_de_praca")

        if resolved_fields:
            record.pending_fields = [
                pending
                for pending in record.pending_fields
                if pending.field_name not in resolved_fields
            ]

        return record