from modules.gestao_pessoal.application.services import GestaoPessoalService
from modules.compilador.application.services import (
    CompilerIntegrationService,
    RealCompilerPipelineService,
)
from modules.compilador.application.compile_record import CompileRecordUseCase
from modules.compilador.application.apply_pending_resolution import ApplyPendingResolutionUseCase
from modules.compilador.application.render_odt import RenderOdtUseCase
from modules.compilador.application.pipeline import CompilerDocumentPipeline

class AppContainer:
    def __init__(self) -> None:
        self.app_name = "SisGeS"
        self.gestao_pessoal = GestaoPessoalService()
        self.compiler_integration = CompilerIntegrationService(self.gestao_pessoal)
        self.compile_record_use_case = CompileRecordUseCase(self.compiler_integration)
        self.real_compiler_pipeline = RealCompilerPipelineService(self.compiler_integration)
        self.apply_pending_resolution_use_case = ApplyPendingResolutionUseCase()
        self.render_odt_use_case = RenderOdtUseCase()
        self.compiler_document_pipeline = CompilerDocumentPipeline(
            compiler=self.real_compiler_pipeline,
            renderer=self.render_odt_use_case,
        )


    def health(self) -> dict:
        return {
            "app": self.app_name,
            "status": "ok",
        }


container = AppContainer()
