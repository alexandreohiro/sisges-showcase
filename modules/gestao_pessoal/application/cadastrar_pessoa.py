from modules.gestao_pessoal.domain.entities import Militar
from modules.gestao_pessoal.application.services import GestaoPessoalService


class CadastrarPessoaUseCase:
    def __init__(self, service: GestaoPessoalService) -> None:
        self.service = service

    def execute(self, militar: Militar) -> Militar:
        self.service._militares.append(militar)
        return militar