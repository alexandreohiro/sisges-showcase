from modules.gestao_pessoal.application.services import GestaoPessoalService


class BuscarPessoaUseCase:
    def __init__(self, service: GestaoPessoalService) -> None:
        self.service = service

    def por_identidade(self, identidade: str):
        return self.service.buscar_por_identidade(identidade)

    def por_nome(self, termo: str):
        return self.service.buscar_por_nome(termo)