# SisGeS

Sistema de Gerenciamento de Secretaria.

> **Nota de proveniência:** este repositório público é uma versão saneada do
> projeto original, publicada para fins de avaliação técnica e portfólio.
> O histórico de desenvolvimento interno (commits granulares, iteração
> diária) é mantido em um repositório privado separado, por proteção de
> dados pessoais de militares processados pelo sistema durante o
> desenvolvimento. Este repositório nasce de um único commit inicial,
> auditado, sem nenhum dado real de pessoas — qualquer exemplo, fixture
> ou dado de teste aqui presente é sintético.
>
> Ver `LICENSE` antes de reutilizar, copiar ou implantar este código:
> uso, cópia, modificação ou implantação em produção por terceiros não
> é autorizado sem permissão explícita do autor.

## Objetivo

O SisGeS e um backend para apoiar rotinas de secretaria, com foco inicial em gestao de pessoal militar, compilacao de documentos, folhas de alteracao, tarefas, documentos gerados e calculo de tempo de servico.

## Stack

- Python 3.11+
- FastAPI + Uvicorn
- SQLAlchemy 2.x
- SQLite para desenvolvimento local
- Jinja2 para paginas server-side

## Setup

```bash
python -m pip install -e ".[dev]"
```

## Run

```bash
python -m uvicorn apps.web.app:app --reload
```

Acesse:

- App: http://127.0.0.1:8000
- Healthcheck: http://127.0.0.1:8000/health
- OpenAPI: http://127.0.0.1:8000/docs

### Execucao local em LAN

Para uso operacional local com o frontend Next.js em `3001`, rode o backend em `3031`:

```powershell
cd "C:\caminho\para\sisges"
powershell -ExecutionPolicy Bypass -File .\scripts\start_sisges_backend_lan.ps1
```

O procedimento completo de start/stop, IP de rede, CORS e validacao esta em `docs/EXECUCAO_LOCAL_LAN_SISGES.md`.

Para conferir se a LAN esta operacional:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\validate_sisges_lan.ps1
```

Para validar a pilha operacional principal, incluindo backend Folhas e frontend:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\validate_sisges_operational_stack.ps1
```

## Test

```bash
python -m pytest
```

## Lint

```bash
python -m ruff check .
```

## Banco local

O banco padrao de desenvolvimento fica em `data/sisges.db`.

Para criar/atualizar schema:

```bash
python -m alembic upgrade head
```

Para aplicar seed basico de papeis, permissoes e feature flags:

```bash
python -m infra.persistence.seed
```

Bootstrap oficial de ambiente local/pre-producao:

```bash
python -m scripts.bootstrap
```

O seed nao cria usuario com senha padrao. Para criar ou atualizar um admin inicial, defina:

```bash
SISGES_BOOTSTRAP_ADMIN_USERNAME=admin
SISGES_BOOTSTRAP_ADMIN_PASSWORD=<senha-forte-com-12-ou-mais-caracteres>
python -m infra.persistence.seed
```

## Variaveis de ambiente principais

- `SISGES_ENV`: ambiente de execucao (`dev`, `test` ou `prod`). Padrao: `dev`.
- `SISGES_DATABASE_URL`: URL SQLAlchemy do banco. Obrigatoria em `SISGES_ENV=prod`.
- `SISGES_HOST`: host sugerido para execucao local. Padrao: `127.0.0.1`.
- `SISGES_PORT`: porta sugerida para execucao local. Padrao: `8000`.
- `SISGES_DEBUG`: habilita modo debug quando `true`.
- `SISGES_FRONTEND_ORIGINS`: origens CORS adicionais separadas por virgula.
- `SISGES_SECRET_KEY`: segredo usado para assinar sessoes. Obrigatorio e forte em `prod`.
- `SISGES_VAULT_KEY`: segredo usado para cifrar o vault de auditoria de credenciais. Deve ser diferente de `SISGES_SECRET_KEY`. Obrigatorio e forte em `prod`.
- `SISGES_SESSION_COOKIE_NAME`: nome do cookie de sessao. Padrao: `session_token`.
- `SISGES_SESSION_COOKIE_SECURE`: usa cookie apenas em HTTPS quando `true`. Padrao: `true` em `prod`.
- `SISGES_SESSION_COOKIE_SAMESITE`: `lax`, `strict` ou `none`. Padrao: `lax`.
- `SISGES_SESSION_MAX_AGE_SECONDS`: validade da sessao assinada. Padrao: `43200`.
- `SISGES_BOOTSTRAP_ADMIN_*`: variaveis opcionais para criar usuario inicial via seed.
- `SISGES_LOG_LEVEL`: nivel de log (`INFO`, `DEBUG`, `WARNING`, `ERROR`). Padrao: `INFO`.
- `SISGES_LOG_FORMAT`: `json` ou `text`. Padrao: `json`.
- `SISGES_WORKSPACE_RETENTION_HOURS`: idade maxima de workspaces temporarios antes da limpeza. Padrao: `24`.

## Operacao

Healthchecks:

- `/health/live`: processo HTTP vivo.
- `/health/ready`: pronto para receber trafego, com consulta real ao banco.
- `/health`: diagnostico operacional com ambiente, debug e status do banco.

Limpeza manual de workspaces antigos do compilador:

```bash
python -m scripts.cleanup_workspaces --retention-hours 24
python -m scripts.cleanup_workspaces --dry-run
```

Gate local de pre-release:

```bash
python -m scripts.sisges_release_gate --run-validation
```

Para validar tambem o pacote congelado de entrega:

```bash
python -m scripts.sisges_release_gate \
  --run-validation \
  --release-package data/output/PACOTE_ENTREGA_SECRETARIA_REVISADO.zip
```

Para incluir regressao de timing dos endpoints criticos:

```bash
python -m scripts.sisges_release_gate \
  --run-validation \
  --run-security-preflight \
  --check-frontend-csrf \
  --run-host-security-preflight \
  --check-nginx-syntax \
  --run-health-smoke \
  --run-overclock \
  --ux-ui-report data/output/ux_ui_overclock/RELATORIO_UX_UI_OVERCLOCK.json \
  --release-package data/output/PACOTE_ENTREGA_SECRETARIA_REVISADO.zip
```

O gate verifica `.gitignore`, presenca de Git, arquivos proibidos staged/tracked quando Git estiver disponivel, exemplos de artefatos locais, hash SHA-256 do pacote informado e, quando `--run-validation` e usado, executa `ruff`, `pytest`, validacao CSRF do frontend e build do frontend configurado. Quando `--run-security-preflight` e usado, executa o preflight defensivo do backend e pode validar o contrato CSRF do frontend com `--check-frontend-csrf`. Quando `--run-host-security-preflight` e usado, valida a postura local do host e pode testar a sintaxe do Nginx com `--check-nginx-syntax`. Quando `--run-health-smoke` e usado, valida `/health/live`, `/health/ready` e `/health` via app local e grava `data/output/sisges_release_gate_health.*`. Quando `--run-overclock` e usado, executa o perfil critico de timing em `ops/overclock/critical_endpoints.txt`, grava evidencia local em `data/output/sisges_release_gate_overclock.*` e incorpora no relatorio principal o status, endpoint mais lento e regressoes detectadas. Quando `--ux-ui-report` e informado, valida o relatorio de navegacao autenticada contra `ops/ux_ui/critical_pages.json` e bloqueia o gate se uma tela critica falhar. Artefatos em `data/`, bancos, PDFs, ODTs, ZIPs e screenshots nao devem ser commitados.

Para promover uma medicao OK para baseline local de timing:

```bash
python -m scripts.operational_overclock_baseline promote \
  --source data/output/operational_overclock_timings.json \
  --output-json data/output/operational_overclock_baseline.json \
  --profile critical
```

Esse comando valida o relatorio antes da copia e gera manifesto local com hash em `data/output/operational_overclock_baseline_manifest.*`.

## Compilador de Folhas de Alterações

O Compilador transforma SiCaPEx, PDFs de alterações, modelo ODT oficial e cálculo de tempo em Folhas de Alterações auditáveis. Cada geração deve produzir ODT, PDF, validação, justificativa, `variables.json` e pacote individual, preservando hash, memória documental e rastreabilidade.

O processo separa folhas prontas para assinatura, folhas para revisar manualmente e folhas bloqueadas. O modelo ODT oficial deve ser usado quando informado; dados como QMS/QM passam por normalização; a 1ª Parte organiza eventos por mês; a 2ª Parte depende do contexto de tempo de serviço e deve explicitar origem e pendências.

Documentação operacional:

- `docs/COMPILADOR_FOLHAS_ALTERACOES_PROCESSO.md`: processo completo, regras, validações e lógica documental.
- `docs/CHECKLIST_OPERADOR_FOLHAS.md`: checklist curto para conferência antes da assinatura.
- `docs/FLUXO_RAPIDO_ENTREGA_FOLHAS.md`: sequência de execução para importar, gerar, revisar e empacotar.
- `docs/ERROS_E_HOTFIX_FOLHAS.md`: tabela de erros, causas, impacto e hotfix.

## Estado tecnico

Este projeto esta em evolucao incremental. A Fase 1 da reconstrucao prioriza higiene de repositorio, testes executaveis, documentacao minima e correcao de duplicacoes perigosas nos modelos SQLAlchemy.
