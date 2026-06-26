from .home import router as home_router
from .health import router as health_router
from .compilador import router as compilador_router
from .gestao_pessoal import router as gestao_pessoal_router
from .declaracoes import router as declaracoes_router
from .ctsm import router as ctsm_router
from .ops_center import router as ops_center_router
from .militar_360 import router as militar_360_router
from .consistencia import router as consistencia_router
from .acoes_sugeridas import router as acoes_sugeridas_router

__all__ = [
    "home_router",
    "health_router",
    "compilador_router",
    "gestao_pessoal_router",
    "declaracoes_router",
    "ctsm_router",
    "ops_center_router",
    "militar_360_router",
    "consistencia_router",
    "acoes_sugeridas_router",
]
