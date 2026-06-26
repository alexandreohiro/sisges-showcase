# Reconstrucao tecnica do backend SISGES - Fase 6

Data: 2026-05-03

## 1. Diagnostico da fase

O backend ja subia e possuia `/health`, mas o endpoint nao testava banco. O logging existia como pacote vazio, nao havia bootstrap operacional unico, e workspaces temporarios do compilador dependiam apenas da limpeza por contexto. A configuracao tambem nao documentava variaveis de observabilidade e retencao.

## 2. Arquitetura-alvo

- `infra/logging/setup.py`: configuracao central de logs estruturados.
- `infra/persistence/health.py`: diagnostico real de banco.
- `apps/web/routes/health.py`: healthcheck live/readiness/diagnostico.
- `scripts/bootstrap.py`: comando oficial para migration, seed e limpeza inicial.
- `infra/pipeline/cleanup.py`: rotina reutilizavel de limpeza de workspaces antigos.
- `scripts/cleanup_workspaces.py`: entrada operacional para limpeza manual/agendada.

## 3. Arquivos criados/alterados

- Alterados: `infra/config.py`, `.env.example`, `README.md`, `apps/web/app.py`, `apps/web/routes/health.py`.
- Criados: `infra/persistence/health.py`, `infra/pipeline/cleanup.py`, `scripts/bootstrap.py`, `scripts/cleanup_workspaces.py`.

## 4. Codigo por arquivo

Os arquivos foram aplicados diretamente no repositorio. Pontos de entrada:

- `python -m scripts.bootstrap`
- `python -m scripts.cleanup_workspaces --retention-hours 24`
- `GET /health`
- `GET /health/live`
- `GET /health/ready`

## 5. Criterios de aceite

- Logs devem sair em JSON por padrao.
- `/health/ready` deve executar `select 1`.
- Falha de banco deve retornar status HTTP 503 nos checks de prontidao.
- Bootstrap deve aplicar Alembic, seed e limpeza de workspace.
- Limpeza deve suportar `dry-run`.
- `.env.example` deve listar variaveis operacionais.

## 6. Riscos restantes

- Logs estruturados ainda nao possuem correlation id por requisicao.
- Nao ha endpoint autenticado de diagnostico profundo.
- Limpeza periodica depende de agendamento externo no Windows/Linux.
- Banco externo esta preparado por `SISGES_DATABASE_URL`, mas pool/tuning especifico de PostgreSQL deve ser calibrado em pre-producao.

## 7. Rollback

1. Reverter `apps/web/routes/health.py` para resposta simples.
2. Remover chamada a `configure_logging()` em `apps/web/app.py`.
3. Remover scripts de bootstrap/limpeza.
4. Remover variaveis novas do `.env.example` se o ambiente ainda nao as usar.
