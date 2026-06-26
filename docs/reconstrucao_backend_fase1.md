# Reconstrucao tecnica do backend SISGES - Fase 1

Data: 2026-05-03

## 1. Diagnostico executivo

O backend SISGES ja possui uma base funcional em FastAPI com separacao inicial por dominios, persistencia SQLAlchemy e modulos importantes para secretaria: autenticacao, gestao de pessoal, compilador documental, folhas, tarefas, documentos e calculo de tempo de servico.

A principal fragilidade da Fase 1 nao e ausencia de sistema, mas falta de base operacional confiavel para evolucao: arquivos locais nao ignorados, testes nao executaveis, README quebrado, modelos SQLAlchemy com sobrescritas internas e schemas Pydantic com campos duplicados ou nao persistidos.

O compilador deve ser tratado nas fases seguintes como subsistema critico e auditavel. Nesta fase, a decisao foi nao mexer no pipeline PDF/ODT para evitar misturar higiene estrutural com redesenho de fluxo documental.

## 2. Arquitetura-alvo proposta

A arquitetura-alvo preserva a estrutura atual e endurece responsabilidades por camada:

- `apps/web`: entrada HTTP, rotas FastAPI, templates e dependencias de request.
- `modules/<dominio>`: regras de negocio, casos de uso, DTOs e schemas do dominio.
- `infra/persistence`: engine, modelos ORM e repositorios sem decisao transacional final.
- `infra/security`: hash, tokens, sessao e politicas de autenticacao.
- `infra/pdf` e `infra/odt`: capacidades tecnicas do pipeline documental.
- `shared`: erros, tipos, contratos e utilitarios transversais.

Decisao arquitetural: manter monolito modular. O sistema ainda nao justifica servicos separados; o ganho imediato vem de fronteiras internas claras, testes executaveis, transacoes controladas por caso de uso e pipeline documental rastreavel.

## 3. Plano da Fase 1

Escopo aplicado nesta fase:

- Corrigir `.gitignore`.
- Declarar dependencias de desenvolvimento e teste.
- Reescrever README minimo reproduzivel.
- Verificar encoding real dos arquivos.
- Remover sobrescritas perigosas dos modelos SQLAlchemy.
- Remover duplicacao de campos em schema Pydantic.
- Alinhar campos de update/read de gestao pessoal ao modelo persistido atual.
- Adicionar testes minimos de import da app e criacao de schema.

Fora de escopo nesta fase:

- Alembic/migrations formais.
- Refatoracao transacional dos repositorios.
- Redesenho do compilador PDF/ODT.
- Mudancas de seguranca de sessao.
- Migracao do banco SQLite existente.

## 4. Execucao realizada

Arquivos alterados:

- `.gitignore`: passou a ignorar ambiente virtual, caches, banco local, logs, `.env`, builds e outputs gerados.
- `pyproject.toml`: adicionou extra `dev` com `pytest`, `httpx` e `ruff`, alem de configuracao minima de pytest/ruff.
- `README.md`: substituiu markdown quebrado por guia minimo de setup, run, test, lint, banco e variaveis.
- `infra/persistence/models.py`: removeu duplicidade de `MilitarModel.periodos_servico` e triplicacao interna de `MilitarPeriodoServicoModel`.
- `modules/gestao_pessoal/application/schemas.py`: removeu campos repetidos em `MilitarUpdate` e campos de tempo publico que nao existem no modelo persistido atual.
- `tests/integration/test_app_import.py`: valida import da app e healthcheck.
- `tests/unit/test_persistence_models.py`: valida criacao de schema em SQLite em memoria e ausencia das duplicacoes corrigidas.

## 5. Criterios de pronto da Fase 1

- A aplicacao deve importar sem erro.
- A app deve registrar rotas FastAPI.
- `Base.metadata.create_all()` deve funcionar em SQLite em memoria.
- `MilitarModel` deve ter apenas um relacionamento `periodos_servico`.
- `MilitarPeriodoServicoModel` deve ter uma unica declaracao coerente de colunas.
- `python -m pytest` deve ser executavel apos instalar dependencias de desenvolvimento.
- O README deve permitir setup local reproduzivel.

## 6. Riscos e trade-offs

- Campos `tempo_servico_publico_*` foram removidos dos schemas de gestao pessoal porque nao existem no modelo ORM nem no banco SQLite atual. Reintroducao deve ocorrer na Fase 2 via migration formal.
- O banco local existente nao foi alterado nesta fase. Isso reduz risco operacional, mas deixa mudancas de schema para o plano de migrations.
- A limpeza de encoding foi tratada com verificacao, nao com regravacao ampla: a maioria dos arquivos esta em UTF-8 correto, apesar de exibicao ruim no PowerShell.

## 7. Rollback

Rollback seguro da Fase 1:

1. Reverter alteracoes em `.gitignore`, `pyproject.toml`, `README.md`, `infra/persistence/models.py`, `modules/gestao_pessoal/application/schemas.py` e testes adicionados.
2. Nenhuma migracao de banco foi aplicada.
3. Nenhum dado local foi modificado.

