# Fechamento Tecnico - Ciclo SISGES Folhas de Alteracoes

## 1. Objetivo do ciclo

Este ciclo consolidou o fluxo operacional de geracao, validacao, revisao, empacotamento e homologacao das Folhas de Alteracoes no SISGES.

O objetivo tecnico foi transformar fontes dispersas em documentos auditaveis: SiCaPEx, fontes de alteracoes/BI, banco de Gestao de Pessoal, calculo de tempo de servico, memoria do Compilador, modelo ODT oficial ou modelo interno, validacoes e pacotes finais.

O resultado esperado era entregar uma rotina de secretaria que nao dependesse de sucesso falso, mock ou processamento manual invisivel. Cada folha precisa ter origem rastreavel, validacao clara e pendencias separadas.

## 2. Pacote de entrega congelado

A entrega operacional revisada foi congelada como pacote final de secretaria.

Pacote principal:

```text
data/output/PACOTE_ENTREGA_SECRETARIA_REVISADO.zip
```

O pacote congelado nao deve ser substituido, reprocessado ou alterado sem abertura de novo ciclo, nova validacao, novo hash e nova release operacional.

## 3. Hash da release

SHA-256 confirmado da release congelada:

```text
72168331c07985192019c049e16ed9146245d4f9290c621ca7bdae12fa602abf
```

Esse hash e a referencia de integridade do pacote revisado. Qualquer divergencia indica que o artefato foi alterado ou substituido.

## 4. Quantitativo

Resultado operacional do pacote revisado:

- Folhas prontas para assinatura: 48
- Folhas para revisar manualmente: 4
- Folhas bloqueadas: 0

As folhas em revisao manual nao representam falha oculta. Elas foram separadas porque exigem conferencia humana, principalmente em pontos de tempo de servico, warnings documentais ou decisao administrativa.

## 5. Commits principais

Commits relevantes do ciclo:

- `f346e94 feat(compilador): add visual format contract for folhas`
  - Fechou o contrato visual/formal baseado na referência visual ODT.
  - Separou formato documental de semantica de filtragem.
  - Garantiu filtro de eventos desligado por padrao.

- `3d106f4 fix(compilador): align BI inputs, default template and conditional sicapex flow`
  - Alinhou backend do Compilador para roles corretos, pacote completo, modelo interno e SiCaPEx condicional.
  - Adicionou suporte a compilacao a partir da memoria.

- `991a837 fix(compilador): support BI source roles and conditional sicapex upload in UI`
  - Alinhou frontend do Compilador com PDF/ODT de alteracoes, memoria, modelo opcional e upload SiCaPEx condicional.

## 6. Funcionalidades implementadas

Principais capacidades fechadas:

- Importacao e uso de fontes de alteracoes por PDF e ODT.
- Roles formais para inputs:
  - `INPUT_BI_PDF`
  - `INPUT_BI_ODT`
  - `INPUT_SICAPEX_PDF`
  - `INPUT_MODELO_ODT`
  - `INTERNAL_DEFAULT_MODELO_ODT`
  - `MEMORY_REFERENCE_BI_PDF`
  - `MEMORY_REFERENCE_BI_ODT`
  - `MEMORY_REFERENCE_FOLHA_PDF`
- Modelo ODT opcional, com fallback para modelo interno gerado por codigo.
- Contrato visual/formal para Folhas de Alteracoes.
- Modo de mes vazio configuravel:
  - `BLOCK`
  - `COMPACT_SINGULAR`
  - `COMPACT_PLURAL`
- Validacao de ODT em `content.xml` e `styles.xml`.
- Header reconhecido tanto no corpo quanto em header/master-page/styles.
- QMS/QM normalizado para cabecalho.
- SiCaPEx condicional:
  - banco completo nao exige PDF;
  - banco incompleto exige fonte complementar.
- `compile-from-memory`, sem depender de upload local.
- Pacote completo do Compilador com:
  - ODT;
  - ODT separado da 1ª Parte (`parte_1_alteracoes.odt`) nas novas compilações;
  - PDF quando disponivel;
  - `validacao.txt`;
  - `justificativa.txt`;
  - `variables.json`;
  - `compiler_run.json`;
  - `manifest.json`.
- Headers de resposta para o frontend:
  - `X-Sisges-Compiler-Run-Id`;
  - `X-Sisges-Document-Id`;
  - `X-Sisges-Package-Mode`.
- Homologacao frontend do fluxo do Compilador.
- Rotina operacional de release e triagem de workspace.

## 7. Validacoes executadas

Validacoes tecnicas executadas durante o fechamento:

- Testes do contrato visual ODT de referência.
- Testes de modos de mes vazio.
- Testes de politica de filtro de eventos.
- Testes de normalizacao QMS.
- Testes de renderizacao ODT por template.
- Testes de cabecalho da Folha.
- Testes de memoria do Compilador.
- Testes de pacote completo.
- Testes de compilacao a partir da memoria.
- Testes de roles de input.
- Testes de modelo interno.
- Testes de SiCaPEx condicional.
- `ruff check`.
- `npm run build` no frontend.
- Validacao do hash da release congelada.

Resultado final do saneamento:

- Backend limpo em `develop...origin/develop`.
- Frontend limpo em `develop...origin/develop`.
- Nenhum artefato operacional versionado.

## 8. O que ficou fora do Git

Foram mantidos fora do Git:

- `data/output/`
- `data/releases/`
- bancos locais;
- PDFs reais;
- ODTs reais;
- ZIPs de entrega;
- screenshots;
- relatorios gerados localmente;
- outputs de homologacao;
- arquivos temporarios de validacao.

Essa separacao e intencional. O Git guarda codigo, testes e documentacao. Os artefatos operacionais ficam no ambiente de entrega, com hash e manifesto.

## 9. O que nao deve ser alterado

Nao alterar sem novo ciclo formal:

- pacote revisado congelado;
- release operacional congelada;
- hash de referencia;
- arquivos finais entregues a secretaria;
- banco local usado como evidencia operacional;
- outputs de validacao ja anexados ao pacote.

Tambem nao se deve reprocessar folhas prontas apenas por ajuste cosmetico. Qualquer reprocessamento deve gerar nova versao, novo relatorio, novo hash e registro de motivo.

## 10. Proximas melhorias pos-entrega

Melhorias recomendadas para ciclo posterior:

- Criar painel de acompanhamento de pendencias por tipo e prioridade.
- Melhorar reparo de tabelas complexas em PDFs.
- Ampliar extracao de eventos por referencia de BI.
- Formalizar politica de filtragem por OM, com aprovacao administrativa.
- Tornar a validacao visual mais automatizada.
- Melhorar conversao PDF em ambientes sem LibreOffice.
- Padronizar relatorios de divergencia de tempo de servico.
- Criar teste e2e automatizado do Compilador no frontend.
- Consolidar reprocessamento individual com diff antes/depois.

Essas melhorias nao devem mexer no pacote congelado. Devem abrir novo ciclo de desenvolvimento e homologacao.

## 11. Riscos conhecidos

Riscos residuais:

- Algumas folhas dependem de validacao humana de tempo de servico.
- Eventos filtraveis por privacidade ainda exigem politica formal da OM.
- PDF preview pode depender do conversor disponivel no ambiente.
- Tabelas extraidas de PDF podem exigir revisao manual.
- O modelo interno e fallback operacional; quando houver modelo oficial da OM, ele deve ser preferido.
- Diferencas normativas devem ser validadas pela secretaria conforme norma vigente e modelo oficial adotado pela OM.

## 12. Procedimento de retomada

Para retomar o ciclo com seguranca:

1. Confirmar que o workspace esta limpo.
2. Confirmar o hash do pacote congelado.
3. Ler os documentos operacionais do Compilador.
4. Rodar testes criticos do backend.
5. Rodar `ruff check`.
6. Rodar `npm run build` no frontend se houver alteracao de UI.
7. Criar nova branch ou commit de ciclo posterior.
8. Nunca sobrescrever o pacote congelado.
9. Gerar novo pacote em outro diretorio de saida.
10. Calcular novo hash e registrar nova release se houver nova entrega.

Comando de referencia para resumo operacional:

```bash
python -m scripts.secretaria_operacional resumo
```

Comando de referencia para validar release:

```bash
python -m scripts.secretaria_release validar --release data/releases/secretaria_folhas_2025_revisado
```

Este fechamento encerra o ciclo atual como entrega operacional rastreavel, com codigo, documentacao e pacote de secretaria separados por responsabilidade.
