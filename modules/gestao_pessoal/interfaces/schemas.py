from pydantic import BaseModel


class MilitarResponse(BaseModel):
    id_interno: str
    nome_completo: str
    nome_guerra: str
    graduacao: str
    identidade: str
    qm: str
    om: str
    guarnicao: str
    data_de_praca: str