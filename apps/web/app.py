from os import getenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from apps.web.config import APP_NAME, APP_VERSION, STATIC_DIR
from apps.web.middleware.csrf import CsrfProtectionMiddleware
from apps.web.routes.home import router as home_router
from apps.web.routes.health import router as health_router
from apps.web.routes.compilador import router as compilador_router
from apps.web.routes.compilador_folha import router as compilador_folha_router
from apps.web.routes.compilador_documentos import router as compilador_documentos_router
from apps.web.routes.compilador_memory import router as compilador_memory_router

from apps.web.routes.declaracoes import router as declaracoes_router
from apps.web.routes.documents import router as documents_router
from apps.web.routes.auth import router as auth_router
from apps.web.routes.users import router as users_router
from apps.web.routes.roles import router as roles_router
from apps.web.routes.feature_flags import router as feature_flags_router
from apps.web.routes.dashboard import router as dashboard_router
from apps.web.routes.gestao_pessoal import router as gestao_pessoal_router
from apps.web.routes.tarefas import router as tarefas_router
from apps.web.routes.folhas import router as folhas_router
from apps.web.routes.ctsm import router as ctsm_router
from apps.web.routes.ops_center import router as ops_center_router
from apps.web.routes.militar_360 import router as militar_360_router
from apps.web.routes.consistencia import router as consistencia_router
from apps.web.routes.acoes_sugeridas import router as acoes_sugeridas_router
from apps.web.routes.quadro import router as quadro_router

from apps.web.routes.calculo_tempo_servico import router as calculo_tempo_servico_router
from infra.logging.setup import configure_logging

DEFAULT_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://10.67.171.173:3000",
    "http://10.67.171.173:3001",
    "http://192.168.0.109:3000",
    "http://192.168.0.109:3001",
]

extra_origins = getenv("SISGES_FRONTEND_ORIGINS", "")
EXTRA_ORIGINS = [item.strip() for item in extra_origins.split(",") if item.strip()]

ALLOWED_ORIGINS = list(dict.fromkeys(DEFAULT_ORIGINS + EXTRA_ORIGINS))


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title=APP_NAME,
        version=APP_VERSION,
    )

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    app.add_middleware(CsrfProtectionMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "Content-Disposition",
            "X-Sisges-Compiler-Run-Id",
            "X-Sisges-Document-Id",
            "X-Sisges-Package-Mode",
            "X-Sisges-Folhas-Generation-Status",
            "X-Sisges-Folhas-Warnings-Count",
        ],
    )

    app.include_router(home_router)
    app.include_router(health_router)
    app.include_router(compilador_router)
    app.include_router(compilador_folha_router)
    app.include_router(compilador_documentos_router)
    app.include_router(compilador_memory_router)
    app.include_router(gestao_pessoal_router)
    app.include_router(declaracoes_router)
    app.include_router(documents_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(roles_router)
    app.include_router(feature_flags_router)
    app.include_router(dashboard_router)
    app.include_router(tarefas_router)
    app.include_router(folhas_router)
    app.include_router(ctsm_router)
    app.include_router(ops_center_router)
    app.include_router(militar_360_router)
    app.include_router(consistencia_router)
    app.include_router(acoes_sugeridas_router)
    app.include_router(calculo_tempo_servico_router)
    app.include_router(quadro_router)

    return app


app = create_app()
