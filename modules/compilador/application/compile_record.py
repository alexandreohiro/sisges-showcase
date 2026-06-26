from modules.compilador.domain.parser import parse_record
from modules.compilador.application.services import CompilerIntegrationService
from modules.gestao_pessoal.submodulos.gestao_tempo import obter_perfil_tempo_por_identidade


class CompileRecordUseCase:
    def __init__(self, integration_service: CompilerIntegrationService) -> None:
        self.integration_service = integration_service

    def execute(self, text: str):
        record = parse_record(text)
        record = self.integration_service.enrich_record(record)

        # fallback de tempo só entra se a extração não trouxe os campos principais
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

        return record