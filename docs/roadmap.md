# Roadmap técnico

Consolidação do plano de infraestrutura de software em execução desde 2026-06-23. Cada fase tem documentação própria quando aplicável.

## Concluído

- **Fase 0-1 — Contenção e saneamento de histórico git**: exposição pública de dados pessoais detectada e corrigida; histórico privado limpo via `git filter-repo`; chave do vault de credenciais separada da chave de sessão; arquivo morto removido. Ver `docs/SANEAMENTO_HISTORICO_GIT_FASE1.md`.
- **Fase 2 — História pública saneada**: `alexandreohiro/sisges-showcase` criado a partir de cópia auditada, sem histórico herdado. Caminhos pessoais hardcoded removidos de scripts e docs. Ver `docs/SANEAMENTO_HISTORICO_GIT_FASE2.md`.
- **Fase 3 — Governança**: `LICENSE`, `CODEOWNERS`, `CONTRIBUTING.md`, `SECURITY.md`, templates de issue/PR, branch protection, e estas próprias docs estratégicas (`arquitetura.md`, `requisitos.md`, `decisoes_tecnicas.md`, `roadmap.md`).

## Em andamento / próximo

- **Fase 4 — CI/CD (GitHub Actions)**: workflows `ci.yml` (ruff + pytest + release gate), `security.yml` (gitleaks + CodeQL + pip-audit + security preflight), `mysql-hardening.yml` (serviço MySQL efêmero), `dependabot.yml`. Reaproveita os scripts já existentes em `scripts/`.
- **Fase 5 — Backlog MySQL**: executar o plano já detalhado em `docs/PLANO_EVOLUCAO_MYSQL_CLEAN_ARCH.md` (pool configurável — parcialmente pronto —, saneamento de tipos, repositories como fronteira obrigatória, migração real de dados, testes de volume).
- **Fase 6 — Infraestrutura como código**: `Dockerfile`, `docker-compose.yml` (app + MySQL + nginx), `.dockerignore`. Docker tratado como ambiente dev/homolog/CI; produção real pode seguir via Windows Service/IIS se o ambiente do Exército não permitir containers.
- **Fase 7 — Observabilidade mínima**: badges de CI no README, confirmação de `request_id`/correlation id no log JSON.
- **Fase 8 — God-files**: quebrar `modules/calculo_tempo_servico/application/services.py` (~1000 linhas), `modules/compilador/application/folha_alteracoes_compiler.py` (~1480 linhas) e `apps/web/routes/compilador_folha.py` (~1290 linhas) em unidades menores, com `pytest --cov` como rede de segurança antes de cada fatiamento.
- **Fase 9 — Handoff para o frontend**: publicar `docs/openapi.json` via `scripts/export_openapi.py` e `docs/HANDOFF_FRONTEND_SISGES.md`, formalizando o contrato antes de iniciar a re-arquitetura do frontend (`web-sisges-v0`).

## Dívidas conhecidas, não bloqueantes

- Inconsistência de camadas entre módulos (ver `arquitetura.md` — alguns módulos sem `domain/` formal).
- `sisges-showcase` não recebe atualizações automáticas do repositório privado; sincronização é manual.
- Sem framework de teste automatizado equivalente no frontend (scripts `validate:*` customizados em vez de Jest/Vitest/Playwright) — fora do escopo deste repositório.
