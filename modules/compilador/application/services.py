from pathlib import Path

from infra.pdf.extractor import extract_text_from_pdf
from modules.validacao.domain.text_validator import validate_and_fix_text
from modules.validacao.domain.structural_cleaner import clean_structural_noise
from modules.compilador.domain.parser import parse_record
from modules.compilador.domain.entities import CompilationRecord, PendingField
from modules.compilador.domain.rules import is_invalid_qm_value
from modules.gestao_pessoal.application.services import GestaoPessoalService
from modules.gestao_pessoal.submodulos.gestao_tempo import obter_perfil_tempo_por_identidade
from modules.gestao_pessoal.domain.rules import nome_guerra_fallback
from modules.validacao.domain.part1_semantic_cleaner import clean_part1_semantics

class CompilerIntegrationService:
    def __init__(self, gestao_pessoal: GestaoPessoalService) -> None:
        self.gestao_pessoal = gestao_pessoal

    def _add_pending(
        self,
        record: CompilationRecord,
        field_name: str,
        reason: str,
        suggested_value: str = "",
    ) -> None:
        already_exists = any(
            pending.field_name == field_name for pending in record.pending_fields
        )
        if not already_exists:
            record.pending_fields.append(
                PendingField(
                    field_name=field_name,
                    reason=reason,
                    suggested_value=suggested_value,
                    source="pending",
                )
            )

    def enrich_record(self, record: CompilationRecord) -> CompilationRecord:
        militar = None

        if record.header.identidade:
            militar = self.gestao_pessoal.buscar_por_identidade(record.header.identidade)

        if not militar and record.header.nome_completo:
            encontrados = self.gestao_pessoal.buscar_por_nome(record.header.nome_completo)
            militar = encontrados[0] if encontrados else None

        # nome completo pode vir do cadastro, mas só se faltar
        if militar and not record.header.nome_completo:
            record.header.nome_completo = militar.nome_completo

        # nome de guerra:
        # 1) usa do cadastro se existir
        # 2) se não existir, cria pendência
        if militar and militar.nome_guerra and not record.header.nome_guerra:
            record.header.nome_guerra = militar.nome_guerra
        elif not record.header.nome_guerra:
            suggested = nome_guerra_fallback(record.header.nome_completo) if record.header.nome_completo else ""
            self._add_pending(
                record,
                field_name="nome_guerra",
                reason="nao_encontrado_no_pdf_e_nao_encontrado_na_gestao",
                suggested_value=suggested,
            )

        # graduação
        if militar and not record.header.graduacao:
            record.header.graduacao = militar.graduacao

        # identidade
        if militar and not record.header.identidade:
            record.header.identidade = militar.identidade

        # QM
        if militar and militar.qm and not is_invalid_qm_value(militar.qm) and (
            not record.header.qm or is_invalid_qm_value(record.header.qm)
        ):
            record.header.qm = militar.qm

        if not record.header.qm or is_invalid_qm_value(record.header.qm):
            record.header.qm = ""
            self._add_pending(
                record,
                field_name="qm",
                reason="valor_generico_detectado" if militar else "nao_encontrado_no_pdf_e_nao_encontrado_na_gestao",
                suggested_value="",
            )

        # data de praça
        if militar and militar.data_de_praca:
            record.header.data_de_praca = militar.data_de_praca.isoformat()

        if not record.header.data_de_praca:
            self._add_pending(
                record,
                field_name="data_de_praca",
                reason="nao_encontrado_no_pdf_e_nao_encontrado_na_gestao",
                suggested_value="",
            )

        return record


class RealCompilerPipelineService:
    def __init__(self, integration_service: CompilerIntegrationService) -> None:
        self.integration_service = integration_service

    def compile_pdf(self, pdf_path: str | Path) -> CompilationRecord:
        extraction = extract_text_from_pdf(pdf_path)

        validated_text, text_diagnostics = validate_and_fix_text(extraction.text)
        cleaned_text, clean_diagnostics = clean_structural_noise(validated_text)
        semantic_text, semantic_diagnostics = clean_part1_semantics(cleaned_text)
        
        record = parse_record(semantic_text)
        record = self.integration_service.enrich_record(record)

        precisa_fallback = not any([
            record.part2.tc,
            record.part2.tscmm,
            record.part2.ttes,
            record.part2.tssd,
            record.part2.tsnr,
        ])

        if precisa_fallback and record.header.identidade:
            perfil_tempo = obter_perfil_tempo_por_identidade(record.header.identidade)
            if perfil_tempo:
                if not record.header.data_de_praca:
                    record.header.data_de_praca = perfil_tempo.data_de_praca.isoformat()
                if not record.header.periodo:
                    record.header.periodo = perfil_tempo.periodo

                record.part2.tc = perfil_tempo.tempos.tc
                record.part2.tc_arreg = perfil_tempo.tempos.tc_arreg
                record.part2.tc_nao_arreg = perfil_tempo.tempos.tc_nao_arreg
                record.part2.tc_transito = perfil_tempo.tempos.tc_transito
                record.part2.tc_instalacao = perfil_tempo.tempos.tc_instalacao
                record.part2.tnc = perfil_tempo.tempos.tnc
                record.part2.tscmm = perfil_tempo.tempos.tscmm
                record.part2.tssd = perfil_tempo.tempos.tssd
                record.part2.tsnr = perfil_tempo.tempos.tsnr
                record.part2.ttes = perfil_tempo.tempos.ttes
                record.part2.origem = "fallback"

        record.diagnostics.extend(text_diagnostics)
        record.diagnostics.extend(clean_diagnostics)
        record.metadata["pages"] = extraction.pages
        record.diagnostics.extend(semantic_diagnostics)

        return record