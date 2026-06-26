# Homologacao Frontend do Compilador

## Resultado Atual

Status: `HOMOLOGADO_COM_RESSALVAS`

Militares testados:

- DELTA NETO DA COSTA, identidade `9990000001`, run `12be0ea1-adc1-412c-9a5f-c997e2cf248b`.
- ECHO HENRIQUE SOUZA OLIVEIRA, identidade `9990000002`, run `0104b172-7a1f-4585-af15-6993f688db7a`.

Foi validado pelo frontend:

- login autenticado;
- acesso a Gestao de Pessoal;
- aba Tempo de Servico;
- memoria do Compilador;
- compilacoes reais contra o backend;
- ZIPs integros;
- ODTs validos;
- ausencia de vazamento de QMS bruto;
- historico do Compilador;
- arquivos registrados por run;
- testes criticos do backend;
- `ruff check`;
- `npm run build`.

## Ressalva de Upload Local

Classificacao: `LIMITACAO_AMBIENTE_CODEX`

Durante a homologacao no Codex In-app Browser, a tentativa de upload local foi bloqueada pela propria superficie de navegador:

```text
File uploads are not supported by Codex In-app Browser
```

Esse bloqueio nao prova falha do frontend do SISGES. A validacao autenticada contra endpoint real foi feita com arquivos preparados e persistidos, e o historico/memoria confirmou os runs gerados.

Para fechar a homologacao fora dessa limitacao, repetir o teste em navegador real da maquina:

1. Abrir o frontend no Chrome, Edge, Firefox ou navegador padrao.
2. Fazer login.
3. Ir ao modulo Compilador.
4. Selecionar os arquivos locais.
5. Executar a compilacao.
6. Baixar o ZIP.
7. Confirmar o run no historico.
8. Registrar o resultado em `data/output/front_validation_v2/`.

Se o upload falhar tambem no navegador real, a classificacao muda para bug do SISGES e deve ser tratada no frontend.

## Ressalva de Pacote ZIP

Na homologacao inicial, o endpoint `/compilador/folha/compile-odt` retornava um ZIP minimo com:

- ODT;
- `validacao.txt`;
- `justificativa.txt`.

Os demais artefatos ficavam disponiveis na memoria/historico do Compilador, mas nao dentro do ZIP baixado pela UI.

A homologacao V2 exige pacote completo por padrao:

- `folha_alteracoes.odt`;
- `parte_1_alteracoes.odt`;
- `folha_alteracoes.pdf`, quando o preview for gerado;
- `validacao.txt`;
- `justificativa.txt`;
- `variables.json`;
- `compiler_run.json`;
- `manifest.json`.

Quando o PDF nao for gerado, o pacote continua valido, mas o `manifest.json` deve registrar `WARN_PDF_PREVIEW_NOT_GENERATED`.

## Alternativa Sem Upload Local

Para ambientes onde o upload local esteja bloqueado ou onde os arquivos ja estejam na memoria do Compilador, a UI deve permitir:

- selecionar a fonte `Usar arquivos da memoria`;
- escolher uma execucao com `INPUT_BI_ODT` e `INPUT_SICAPEX_PDF`;
- reaproveitar `INPUT_MODELO_ODT`, quando existir;
- acionar `/compilador/folha/compile-from-memory`;
- baixar ZIP completo;
- ver `run_id`, `document_id`, modo do pacote e checklist do conteudo baixado.

Essa alternativa nao substitui o teste em navegador real, mas elimina a dependencia operacional de upload local quando as fontes ja foram persistidas.

## Criterio Para HOMOLOGADO

A homologacao sobe para `HOMOLOGADO` quando:

- dois militares compilam pelo frontend;
- os dois ZIPs baixados contem pacote completo ou warning explicito para PDF ausente;
- `variables.json`, `compiler_run.json` e `manifest.json` estao no ZIP;
- os runs aparecem no historico do Compilador;
- a memoria mostra inputs e outputs;
- nao ha erro critico de ODT, template, QMS, meses ou tempo;
- testes backend criticos passam;
- `ruff check` passa;
- `npm run build` passa.

## Homologacao V2

Status: `HOMOLOGADO`

Fluxo validado: `Usar arquivos da memoria`

Resultado:

- DELTA NETO DA COSTA, identidade `9990000001`, run `d4650716-6205-47e4-876e-19491c96fa51`.
- ECHO HENRIQUE SOUZA OLIVEIRA, identidade `9990000002`, run `a9198912-34bc-4716-a795-76845d14edca`.

Os dois runs aparecem no historico do Compilador, com fonte de eventos `MEMORY_FILES` e fonte de tempo `SICAPEX_BANCO_SISGES`.

Os dois ZIPs baixados/gerados pelo frontend foram validados como pacote completo:

- `folha_alteracoes.odt`;
- `parte_1_alteracoes.odt`;
- `validacao.txt`;
- `justificativa.txt`;
- `variables.json`;
- `compiler_run.json`;
- `manifest.json`.

O preview PDF nao foi gerado neste fluxo e foi registrado de forma explicita no `manifest.json` como `WARN_PDF_PREVIEW_NOT_GENERATED`.

Relatorios da homologacao V2:

- `data/output/front_validation_v2/RELATORIO_HOMOLOGACAO_FRONTEND_V2.txt`;
- `data/output/front_validation_v2/RELATORIO_HOMOLOGACAO_FRONTEND_V2.json`.

## Ajuste V3 — papeis de input, modelo padrao e SiCaPEx condicional

O ajuste V3 corrige a semantica operacional do fluxo de Folhas de Alteracoes:

- `Fonte de alteracoes` e `Modelo ODT` sao coisas diferentes.
- PDF de BI/alteracoes deve ser registrado como `INPUT_BI_PDF`.
- ODT de BI/alteracoes deve ser registrado como `INPUT_BI_ODT`.
- PDF ou ODT vindo da memoria preserva role de memoria, como `MEMORY_REFERENCE_BI_PDF`, `MEMORY_REFERENCE_BI_ODT` ou `MEMORY_REFERENCE_FOLHA_PDF`.
- O modelo ODT enviado pelo operador deve ser registrado como `INPUT_MODELO_ODT`.
- Quando o operador nao informa modelo, o SISGES usa `INTERNAL_DEFAULT_MODELO_ODT`.
- O upload de Ficha SiCaPEx so e necessario quando a Gestao de Pessoal nao possui contexto completo.

Checklist V3 pelo frontend:

1. Selecionar militar real.
2. Conferir badge de SiCaPEx no banco.
3. Escolher fonte de alteracoes `Upload PDF`, `Upload ODT` ou `Usar arquivos da memoria`.
4. Deixar `Modelo ODT oficial da OM` vazio para validar o modelo interno.
5. Compilar com pacote completo.
6. Conferir `manifest.json`, `variables.json`, `compiler_run.json` e historico do Compilador.
7. Confirmar que PDF de alteracoes nao virou `INPUT_BI_ODT`.

Resultado esperado: `HOMOLOGADO`, desde que dois militares reais compilem via frontend, o ZIP completo seja baixado e os roles aparecam corretamente no historico.
