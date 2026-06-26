# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/). Datas em `AAAA-MM-DD`. Entradas anteriores a este arquivo foram reconstruídas a partir de `docs/reconstrucao_backend_fase*.md` e dos documentos de saneamento — não são granulares por commit.

## [Unreleased]

### Added
- `LICENSE`, `CODEOWNERS`, `CONTRIBUTING.md`, `SECURITY.md`, templates de issue/PR.
- `docs/arquitetura.md`, `docs/requisitos.md`, `docs/decisoes_tecnicas.md`, `docs/roadmap.md` (antes vazios).
- `SISGES_VAULT_KEY`: chave de criptografia do vault de credenciais separada de `SISGES_SECRET_KEY`.
- Repositório público saneado `alexandreohiro/sisges-showcase`, com história própria (1 commit auditado).

### Changed
- `scripts/secretaria_dataset.py`, `scripts/sisges_release_gate.py`, `scripts/validate_sisges_operational_stack.ps1`: paths de exemplo hardcoded substituídos por variáveis de ambiente (`SISGES_SECRETARIA_INPUT_DIR`, `SISGES_FRONTEND_PATH`).

### Removed
- `modules/validacao/application/validate_compilation.py` (arquivo morto, 0 bytes, sem imports).
- `sisges.egg-info/` deixou de ser rastreado (já coberto por `.gitignore`, mas tracked desde antes da regra existir).

### Security
- Histórico git do repositório privado reescrito via `git filter-repo` após exposição pública acidental de dados pessoais de militares em commits antigos. Ver `docs/SANEAMENTO_HISTORICO_GIT_FASE1.md` e `FASE2.md`.

## 2026-05-03 — Reconstrução técnica (Fases 1-8)

Sequência de fases documentadas individualmente em `docs/reconstrucao_backend_faseN.md`:

- **Fase 1**: correção de `.gitignore`, dependências de dev declaradas, README reescrito, duplicações perigosas em `infra/persistence/models.py` removidas, testes mínimos de import/schema adicionados.
- **Fase 2**: Alembic introduzido com baseline, `infra/config.py` central por ambiente, seed idempotente sem credencial padrão fraca.
- **Fase 3**: sessão revisada (cookie por ambiente, segredo obrigatório forte em prod, erros padronizados em `auth`).
- **Fase 4**: padrão transacional `atomic(db)` introduzido em `infra/persistence/transactions.py`; repositórios deixaram de fazer `commit()` direto; `apps/web/errors.py` para erro HTTP estruturado.
- **Fase 5**: pipeline documental do compilador endurecido — validação de upload, workspace temporário isolado, versionamento de template ODT por hash, rastreabilidade (`trace_id`, hashes) no documento gerado.
- **Fase 6**: observabilidade mínima — logging estruturado JSON, `infra/persistence/health.py`, `/health/live` e `/health/ready` reais, `scripts/bootstrap.py`, limpeza de workspaces antigos.
- **Fase 7**: módulo `ctsm` implementado (cálculo de tempo de serviço militar), com emissão de documento e vínculo a calculo aprovado.
- **Fase 8**: `ops_center` (inbox operacional), `militar_360` (visão consolidada), `consistencia` (motor de regras cruzadas) e `acoes_sugeridas` introduzidos.
