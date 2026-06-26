# Ingestão da Pasta Secretaria no Lançamento

Este documento define como a pasta operacional `secretaria` deve entrar no SISGES durante o ciclo de lançamento LAN/preprodução.

## Regra principal

A pasta `secretaria` não deve ser importada em massa diretamente para o banco.

O fluxo correto é:

1. inventariar;
2. gerar lotes por tipo de ação;
3. aprovar o dry-run por módulo;
4. importar em commit controlado;
5. validar no frontend.

## Comando de inventário

```powershell
cd C:\caminho\para\sisges
.\.venv\Scripts\python.exe -m scripts.secretaria_dataset inventario `
  --input "C:\caminho\para\secretaria" `
  --output data/output/secretaria_dataset `
  --sample-limit 200
```

Saídas locais:

- `data/output/secretaria_dataset/inventario_secretaria.json`
- `data/output/secretaria_dataset/inventario_secretaria.txt`
- `data/output/secretaria_dataset/plano_ingestao_secretaria_lancamento.json`
- `data/output/secretaria_dataset/plano_ingestao_secretaria_lancamento.txt`
- `data/output/secretaria_dataset/lotes/*.csv`

Esses arquivos são operacionais locais e não devem ser commitados.

## Classificação inicial

O SISGES classifica a pasta por subpastas principais:

- `001 - ALTERAÇÕES`: Compilador/Folhas de Alterações.
- `014 - LEGISLAÇÃO`: documentos normativos.
- `015 - PROTOCOLO`: documentos gerais e possíveis tarefas.
- `017 - MATERIAL CARGA`: documentos gerais.
- `018 - HONRA AO MÉRITO`: documentos gerais.
- `020 - POP`: Ajuda operacional.
- `021 - TCMS`: cálculo de tempo/CTSM.
- `022 - CARTA DE RECOMENDAÇÃO`: declarações/modelos.

## Decisão de lançamento

Para o piloto LAN:

- inventário: permitido;
- dry-run por módulo: permitido;
- importação massiva em banco: bloqueada até aprovação;
- produção pública: bloqueada.

## Próxima importação recomendada

Priorizar `001 - ALTERAÇÕES`, porque é a maior fonte e tem vínculo direto com o Compilador de Folhas.

Depois:

1. `022 - CARTA DE RECOMENDAÇÃO` para Declarações;
2. `014 - LEGISLAÇÃO` e `020 - POP` para Ajuda/Documentos;
3. `021 - TCMS` para CTSM/Cálculo;
4. `015 - PROTOCOLO` por amostragem, porque o volume é alto e precisa triagem.

## Restrições

Não versionar:

- PDFs;
- ODTs;
- ZIPs;
- banco local;
- `data/output`;
- `data/input`;
- `data/compiler_memory`;
- relatórios com nomes ou dados sensíveis.

## Validação

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_secretaria_dataset.py
.\.venv\Scripts\python.exe -m ruff check scripts\secretaria_dataset.py tests\test_secretaria_dataset.py
```

## Dry-run inicial de alterações

Após gerar o inventário, executar o dry-run do lote `001 - ALTERAÇÕES`:

```powershell
.\.venv\Scripts\python.exe -m scripts.secretaria_alteracoes_dry_run `
  --input data/output/secretaria_dataset/lotes/importar_como_referencia_compilador_dry_run.csv `
  --output data/output/secretaria_dataset/dry_run_alteracoes `
  --assist-review `
  --review-output data/output/secretaria_dataset/revisao_assistida_alteracoes
```

Esse comando:

- não abre PDFs;
- não grava no banco;
- não copia arquivos para o repositório;
- tenta inferir ano, semestre, posto/graduação e nome apenas pelo nome do arquivo;
- separa entradas prontas para dry-run de referência das entradas que precisam revisão.

Resultado observado no lote atual após inferência por nome de arquivo e pasta pai:

- 6.573 PDFs em `001 - ALTERAÇÕES`;
- 2.857 entradas prontas para dry-run de referência;
- 3.716 entradas exigindo revisão de nome, período ou posto/graduação antes de importação controlada.

Saídas locais:

- `data/output/secretaria_dataset/dry_run_alteracoes/dry_run_alteracoes_001.json`
- `data/output/secretaria_dataset/dry_run_alteracoes/dry_run_alteracoes_001.txt`
- `data/output/secretaria_dataset/dry_run_alteracoes/dry_run_alteracoes_001.csv`

## Revisão assistida

Quando `--assist-review` é usado, o SISGES também gera filas de trabalho para revisão humana:

- `data/output/secretaria_dataset/revisao_assistida_alteracoes/resumo_revisao_assistida_alteracoes.json`
- `data/output/secretaria_dataset/revisao_assistida_alteracoes/resumo_revisao_assistida_alteracoes.txt`
- `data/output/secretaria_dataset/revisao_assistida_alteracoes/revisao_assistida_alteracoes.csv`
- `data/output/secretaria_dataset/revisao_assistida_alteracoes/revisar_nome_nao_identificado.csv`
- `data/output/secretaria_dataset/revisao_assistida_alteracoes/revisar_periodo_nao_identificado.csv`
- `data/output/secretaria_dataset/revisao_assistida_alteracoes/revisar_posto_grad_nao_identificado.csv`
- `data/output/secretaria_dataset/revisao_assistida_alteracoes/prontos_para_referencia_por_nome.csv`
- `data/output/secretaria_dataset/revisao_assistida_alteracoes/por_semestre/*.csv`

Prioridade operacional:

1. Corrigir `revisar_nome_nao_identificado.csv`.
2. Corrigir `revisar_periodo_nao_identificado.csv`.
3. Corrigir `revisar_posto_grad_nao_identificado.csv`.
4. Usar `por_semestre/*.csv` para planejar importação controlada por ano/semestre.

Resultado observado na revisão assistida atual:

- prioridade baixa, pronta para dry-run de referência: 2.857;
- prioridade alta: 3.454;
- prioridade média: 262;
- período não identificado: 3.414;
- nome não identificado: 40;
- posto/graduação não identificado: 262;
- maior fila: `SEM_PERIODO`, com 3.453 entradas.

Essas filas continuam sendo apenas preparação de ingestão. Elas não autorizam gravação no banco sem revisão e aprovação do operador.

## Tipos de origem na revisão assistida

A revisão assistida também separa a origem provável de cada arquivo:

- `FOLHA_ALTERACAO_CANDIDATA`: arquivo ainda candidato ao Compilador;
- `ESCANEAMENTO_TIMESTAMP`: arquivo com nome de escaneamento/data técnica, sem período documental confiável;
- `HISTORICO_ESCANEADO`: arquivo em pasta histórica escaneada, exige conferência;
- `DOCUMENTO_NORMATIVO`: documento de legislação/norma dentro da árvore de alterações;
- `LISTA_GENERICA`: lista ou índice sem militar identificado.

Resultado observado:

- `FOLHA_ALTERACAO_CANDIDATA`: 1.073;
- `ESCANEAMENTO_AVULSO`: 837;
- `ESCANEAMENTO_TIMESTAMP`: 3.205;
- `HISTORICO_ESCANEADO`: 1.450;
- `DOCUMENTO_NORMATIVO`: 7;
- `LISTA_GENERICA`: 1.

Arquivos de apoio:

- `revisar_documento_normativo_ou_generico.csv`;
- `revisar_escaneamento_sem_periodo.csv`.

Regra: `ESCANEAMENTO_TIMESTAMP` não vira período da Folha automaticamente. Data de digitalização não é data documental.
