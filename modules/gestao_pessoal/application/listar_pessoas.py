from modules.gestao_pessoal.application.services import GestaoPessoalService


class ListarPessoasUseCase:
    def __init__(self, service: GestaoPessoalService) -> None:
        self.service = service

    def execute(self):
        return self.service.listar_pessoas()