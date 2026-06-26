from modules.gestao_pessoal.domain.entities import Militar
from modules.gestao_pessoal.interfaces.schemas import MilitarResponse


def present_militar(m: Militar) -> MilitarResponse:
    return MilitarResponse(
        id_interno=m.id_interno,
        nome_completo=m.nome_completo,
        nome_guerra=m.nome_guerra,
        graduacao=m.graduacao,
        identidade=m.identidade,
        qm=m.qm,
        om=m.om,
        guarnicao=m.guarnicao,
        data_de_praca=m.data_de_praca.isoformat(),
    )