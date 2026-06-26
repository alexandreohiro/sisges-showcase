# Arquitetura do SisGeS

## Visão geral

O SisGeS é um monolito modular em Python (FastAPI + SQLAlchemy 2.x), organizado por camadas horizontais (`apps/`, `modules/`, `infra/`, `shared/`) e por módulos de domínio verticais dentro de `modules/`. Não há microsserviços nem fronteiras de rede internas — a separação é só de código/responsabilidade.

```
apps/web/routes/*          # HTTP: validação de entrada, autenticação, permissão
        |
modules/<dominio>/application/   # caso de uso: orquestra domain + infra
        |
modules/<dominio>/domain/        # regra de negócio pura, sem framework (quando existe)
        |
infra/persistence/repositories/  # tradução de regra para persistência
        |
infra/persistence/models.py      # tabelas SQLAlchemy
        |
SQLite (dev) / MySQL (homolog/prod)
```

## Pastas de topo

- `apps/web/`: aplicação FastAPI. `app.py` é a composição raiz (registra middlewares e ~20 routers). `routes/` tem um arquivo por área funcional. `dependencies/` tem `auth.py` (sessão/permissão) e `container.py`. `middleware/csrf.py` implementa CSRF double-submit-cookie.
- `modules/`: 18 módulos de domínio (ver `requisitos.md` para o que cada um faz). Cada módulo é uma pasta com subpastas opcionais `domain/`, `application/`, `infrastructure/`, `interfaces/`.
- `infra/`: infraestrutura compartilhada — `persistence/` (engine, models, repositories, seed, transações), `security/` (hash de senha, tokens de sessão), `pdf/` (extração/OCR), `odt/` (renderização de template), `pipeline/` (workspace/upload/cleanup do compilador), `logging/` (setup + eventos de segurança), `storage/` (arquivos gerados).
- `shared/`: contratos (`dto.py`, `repositories.py`), kernel (`base_models.py`, `errors.py`, `result.py`), tipos (`enums.py`, `aliases.py`) e utilitários transversais (datas, hashing, paths, strings, QMS).
- `migrations/`: Alembic.
- `scripts/`: ferramentas operacionais (importação SiCaPEx, geração/validação de Folhas, gates de release/segurança, backup).
- `ops/`: artefatos operacionais (SQL de usuários MySQL, listas de endpoints críticos para timing).

## Consistência de camadas (estado real, não aspiracional)

Nem todo módulo segue as 4 camadas. Hoje:

**Com `domain/` + `application/` (e às vezes `infrastructure/`/`interfaces/`):** `compilador`, `declaracoes`, `documents`, `gestao_pessoal`, `tarefas`, `validacao`.

**Só `application/services.py`** (lógica simples, sem regra de domínio complexa ainda): `auth`, `users`, `permissions`, `roles` (via `permissions`), `ops_center`, `militar_360`, `consistencia`, `acoes_sugeridas`, `quadro`, `ctsm`, `acessos`, `calculo_tempo_servico` (parcialmente — tem `sicapex_context.py` mas não `domain/` formal), `folhas` (tem `infrastructure/repository.py` mas não `domain/`).

Isso não é necessariamente um erro — módulos simples não precisam de 4 camadas. O risco é quando um módulo "simples" acumula regra de negócio real dentro de `services.py` sem nunca ser promovido a ter `domain/` próprio. Hoje o maior risco concreto disso é `modules/calculo_tempo_servico/application/services.py` (~1000 linhas, mistura parsing, classificação, diff, persistência e serialização) — ver `roadmap.md`.

## Persistência

- ORM: SQLAlchemy 2.x, `DeclarativeBase` em `infra/persistence/db.py`.
- Migrations: Alembic, versionado em `migrations/versions/`.
- Banco de dev: SQLite (`data/sisges.db`, nunca commitado).
- Banco alvo de homolog/produção: MySQL (ver `docs/PLANO_EVOLUCAO_MYSQL_CLEAN_ARCH.md` para o backlog de migração, e `decisoes_tecnicas.md` para a decisão registrada).
- Pool de conexão configurável (`infra/config.py` + `infra/persistence/db.py`), aplicado condicionalmente para drivers não-SQLite.
- Transação: repositórios não fazem `commit()`. A fronteira é `infra/persistence/transactions.py::atomic(db)`, usada por serviços/rotas. Fluxos compostos (ex.: criar folha + tarefa + notificação) ficam dentro de uma única unidade transacional.

## Autenticação e segurança

- Sessão: cookie assinado (`itsdangerous.URLSafeTimedSerializer`, chave `SISGES_SECRET_KEY`), não JWT.
- Senha: PBKDF2-HMAC-SHA256, 390k iterações, salt aleatório, comparação constant-time.
- CSRF: double-submit cookie, comparação constant-time, habilitado por padrão em prod.
- Vault de auditoria de credenciais: Fernet, chave própria `SISGES_VAULT_KEY` (separada da chave de sessão desde a correção registrada em `docs/SANEAMENTO_HISTORICO_GIT_FASE1.md`).
- `infra/config.py` recusa subir em `SISGES_ENV=prod` com secret fraco, cookie inseguro ou `samesite` fora de `strict`.

## Pipeline do Compilador (subsistema mais complexo)

`modules/compilador` processa PDFs do SiCaPEx e de Folhas de Alterações, extrai estrutura via `domain/lexer.py` + `domain/parser.py` + `domain/table_parser.py`, resolve pendências e renderiza ODT a partir de template (`infra/odt/`). Cada execução usa um workspace isolado em `infra/pipeline/workspace.py`, limpo por `scripts/cleanup_workspaces.py`. Validação de saída em `modules/validacao/domain/` (estrutural, semântica e de texto).

## Observabilidade

- Healthchecks: `/health/live` (processo vivo), `/health/ready` (banco real), `/health` (diagnóstico).
- Logging estruturado JSON via `infra/logging/setup.py`; eventos de segurança via `infra/logging/security.py`.

## Frontend (fora deste repositório)

O frontend (Next.js 16 / React 19) vive em repositório separado (`web-sisges-v0`) e consome este backend via HTTP/JSON, autenticando por cookie de sessão + header CSRF. Contrato formal via OpenAPI nativo do FastAPI (`/openapi.json`) — ver `docs/HANDOFF_FRONTEND_SISGES.md` quando publicado (Fase 9 do roadmap de infraestrutura).
