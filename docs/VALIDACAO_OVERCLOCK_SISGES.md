# Validacao Overclock SISGES

Este documento consolida a rotina de validacao de carga controlada do SISGES. O objetivo nao e simular producao real em larga escala, mas detectar regressao operacional em CRUD, filtros, tarefas, Gestao de Pessoal, parser PDF, classificacao ODT, exclusao permanente auditavel e endpoints criticos.

## Escopo

Esta validacao cobre:

- listas operacionais de Tarefas e Gestao de Pessoal;
- filtros por militar, patente, divisao e secao;
- transicoes de tarefas;
- rejeicao de status e prioridade invalidos;
- carga sintetica de efetivo;
- dry-run de SiCaPEx;
- politica de upload vazia ou acima do limite;
- classificacao de ODTs sinteticos;
- exclusao permanente com ZIP de recuperacao;
- validacao assistida e dry-run de restauracao do ZIP de recuperacao sem restaurar banco;
- concorrencia controlada de criacao de tarefas;
- timing de endpoints criticos;
- stress de parser PDF com PDFs sinteticos;
- limites reais de upload para PDF/ODT/imagem.

Nao usar dados reais nem pacote congelado nesta rotina.

## Comandos

Executar no backend:

```powershell
cd C:\caminho\para\sisges
.\.venv\Scripts\python.exe -m pytest tests/test_operational_overclock.py tests/test_operational_overclock_report.py tests/test_reference_folha_pdf_stress.py -q
.\.venv\Scripts\python.exe -m scripts.operational_overclock_report --profile critical --output-json data/output/operational_overclock_timings.json --output-txt data/output/operational_overclock_timings.txt
.\.venv\Scripts\python.exe -m scripts.operational_overclock_report --profile critical --tarefas 300 --efetivo 1000 --repeat 5 --profile-label expanded-300-1000
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
```

O perfil versionado `critical` le os endpoints de `ops/overclock/critical_endpoints.txt`. Esse arquivo e o contrato revisavel dos endpoints criticos de rotina. Use `--endpoints-file` apenas para uma rodada excepcional; quando informado, ele tem prioridade sobre o perfil.

Comparacao contra baseline local:

```powershell
cd C:\caminho\para\sisges
.\.venv\Scripts\python.exe -m scripts.operational_overclock_baseline promote `
  --source data/output/operational_overclock_timings.json `
  --output-json data/output/operational_overclock_baseline.json `
  --profile critical `
  --note "baseline local apos validacao operacional"

.\.venv\Scripts\python.exe -m scripts.operational_overclock_report `
  --profile critical `
  --tarefas 300 `
  --efetivo 1000 `
  --repeat 5 `
  --profile-label expanded-300-1000 `
  --baseline-json data/output/operational_overclock_baseline.json `
  --baseline-metric p95 `
  --regression-tolerance-percent 35
```

O comando `scripts.operational_overclock_baseline promote` valida se o JSON esta com `status=OK`, se contem os endpoints do perfil `critical` e se as metricas esperadas existem antes de copiar para baseline. Ele tambem gera manifesto local em `data/output/operational_overclock_baseline_manifest.json` e `.txt`, com hashes SHA-256 de origem e baseline.

Quando a baseline for informada, o relatorio passa a incluir `baseline_comparison`. Se algum endpoint ultrapassar a tolerancia configurada, o status final vira `FAIL`. Endpoints novos ou removidos sao listados como pendencia de comparacao, mas nao falham automaticamente; o bloqueio ocorre por degradacao medida acima do limite.

Gate local de pre-release:

```powershell
cd C:\caminho\para\sisges
.\.venv\Scripts\python.exe -m scripts.sisges_release_gate --run-validation
```

Smoke de saude do backend:

```powershell
.\.venv\Scripts\python.exe -m scripts.sisges_health_smoke
```

O smoke valida `/health/live`, `/health/ready` e `/health` usando o app local. A checagem `ready` exige consulta real ao banco. O comando gera `data/output/sisges_health_smoke.json` e `.txt`.

Para incluir a verificacao do pacote congelado:

```powershell
.\.venv\Scripts\python.exe -m scripts.sisges_release_gate --run-validation --release-package data/output/PACOTE_ENTREGA_SECRETARIA_REVISADO.zip
```

Para incluir tambem o perfil critico de overclock no gate:

```powershell
.\.venv\Scripts\python.exe -m scripts.sisges_release_gate `
  --run-validation `
  --run-health-smoke `
  --run-overclock `
  --release-package data/output/PACOTE_ENTREGA_SECRETARIA_REVISADO.zip
```

O gate grava a evidencia de saude em `data/output/sisges_release_gate_health.json` e `.txt`, e a evidencia do timing em `data/output/sisges_release_gate_overclock.json` e `.txt`. O relatorio principal do gate tambem incorpora os resumos: health status, database status, endpoints com falha, overclock status, quantidade de endpoints, endpoint mais lento por p95, status da baseline e quantidade de regressoes. Esses arquivos continuam locais e nao devem ser versionados.

Se Git nao estiver disponivel no PATH, o gate fica `PENDENTE` mesmo quando os testes passam. Isso e intencional: release operacional exige auditoria de stage/status antes de commit. Quando Git estiver disponivel, o gate tambem bloqueia arquivos proibidos staged/tracked, como `data/output`, bancos, ZIPs, PDFs, ODTs, screenshots, `.next` e `node_modules`.

Para inspecionar um ZIP de lixeira de militar sem restaurar nada:

```powershell
cd C:\caminho\para\sisges
.\.venv\Scripts\python.exe -m scripts.inspect_militar_trash_archive --archive data/trash/gestao_pessoal/militares/ARQUIVO.zip
```

Executar no frontend quando houver alteracao visual ou contrato de tela:

```powershell
cd C:\caminho\para\web-sisges-v0
npm.cmd run build
```

## Evidencias geradas

Os arquivos abaixo sao locais e nao devem ser versionados:

- `data/output/operational_overclock_timings.json`;
- `data/output/operational_overclock_timings.txt`;
- `data/output/operational_overclock_baseline.json`;
- `data/output/operational_overclock_baseline_manifest.json`;
- `data/output/operational_overclock_baseline_manifest.txt`;
- `data/output/sisges_health_smoke.json`;
- `data/output/sisges_health_smoke.txt`;
- `data/output/sisges_release_gate_health.json`;
- `data/output/sisges_release_gate_health.txt`;
- `data/output/lixeira_militar_inspection.json`;
- `data/output/lixeira_militar_inspection.txt`;
- `data/output/overclock_validation_report.txt`;
- screenshots ou resultados responsivos em `data/output`.

## Resultado esperado atual

Na ultima rodada registrada:

- bateria operacional agregada: 17 passed;
- pytest completo: 209 passed;
- ruff: passed;
- build frontend: passed;
- timing operacional: OK;
- maior tempo observado no perfil expandido: `/gestao-pessoal?view_scope=efetivo_completo&limit=180`, abaixo de 210 ms no ambiente local.
- percentis gerados: p50, p90, p95 e p99 por endpoint.
- dry-run de restauracao da lixeira: validado sem escrita automatica no banco.
- CLI de inspecao de lixeira: validado com ZIP sintetico e conflito por identidade.

Os warnings de `datetime.utcnow()` foram saneados no codigo do projeto. A rotina atual fecha sem bloco de warnings no pytest completo.

## Regras de seguranca

- Nao alterar `data/output/PACOTE_ENTREGA_SECRETARIA_REVISADO.zip`.
- Nao alterar `data/releases/secretaria_folhas_2025_revisado`.
- Nao usar PDFs, ODTs ou dados pessoais reais em testes de stress.
- Nao commitar `data/output`, banco SQLite, ZIP, PDF, ODT ou screenshot.
- Testes de carga devem usar SQLite temporario ou `tmp_path`.

## Quando executar

Execute esta rotina:

- antes de fechar release operacional;
- depois de alterar Tarefas, Gestao de Pessoal, upload, Compilador, parser PDF ou templates ODT;
- depois de alterar permissao, seed, filtros ou contratos de API;
- quando houver regressao visual em tela operacional.

## Limites

Esta rotina nao substitui:

- teste manual em navegador real;
- homologacao com operador da secretaria;
- validacao normativa;
- teste de PDF real autorizado;
- teste de banco de producao.

Ela serve para indicar que a base estrutural continua operacional sob carga sintetica controlada.
