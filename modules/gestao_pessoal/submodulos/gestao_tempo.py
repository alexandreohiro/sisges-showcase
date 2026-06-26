from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class TempoParte2:
    tc: str
    tc_arreg: str
    tc_nao_arreg: str
    tc_transito: str
    tc_instalacao: str
    tnc: str
    tscmm: str
    tssd: str
    tsnr: str
    ttes: str
    origem: str  # "extraido" | "fallback"


@dataclass(slots=True)
class PerfilTempoMilitar:
    identidade: str
    data_de_praca: date
    periodo: str
    tempos: TempoParte2


PERFIS_TEMPO = {
    "043507214-5": PerfilTempoMilitar(
        identidade="043507214-5",
        data_de_praca=date(1997, 8, 6),
        periodo="01/07/2025 a 31/12/2025",
        tempos=TempoParte2(
            tc="00a06m00d",
            tc_arreg="00a06m00d",
            tc_nao_arreg="00a00m00d",
            tc_transito="00a00m00d",
            tc_instalacao="00a00m00d",
            tnc="00a00m00d",
            tscmm="28a05m27d",
            tssd="02a06m08d",
            tsnr="00a00m00d",
            ttes="31a00m05d",
            origem="fallback",
        ),
    ),
}


def obter_perfil_tempo_por_identidade(identidade: str) -> PerfilTempoMilitar | None:
    return PERFIS_TEMPO.get(identidade.strip())