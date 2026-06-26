from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class Militar:
    id_interno: str
    nome_completo: str
    nome_guerra: str
    graduacao: str
    identidade: str
    qm: str
    om: str
    guarnicao: str
    data_de_praca: date