# Erros e Hotfix — Folhas de Alterações

| Erro | Causa provável | Comando de correção | Impacto |
| --- | --- | --- | --- |
| `ERR_TEMPLATE_IGNORED` | Modelo ODT foi enviado, mas renderizador usou template interno | `python -m scripts.rebuild_folhas_with_template --input data/output/folhas --modelo data/input/modelos/MODELO_FOLHA.odt --output data/output/folhas_rebuild` | Bloqueia assinatura; documento pode estar fora do padrão visual |
| `ERR_TEMPLATE_ANCHOR_NOT_FOUND` | Modelo não tem placeholders ou anchors reconhecidos | Ajustar modelo ou renderizador; depois reprocessar com `scripts.rebuild_folhas_with_template` | Bloqueia geração confiável |
| `ERR_TEMPLATE_PLACEHOLDER_UNRESOLVED` | Sobrou `[CAMPO]` no ODT final | Reprocessar garantindo substituição em `content.xml` e `styles.xml` | Bloqueia assinatura |
| `ERR_TEMPLATE_PLACEHOLDER_LEFTOVER` | Sobrou `[GRADUACAO]`, `[NOME]`, `[PERIODO]`, `{{...}}` ou `[[SISGES:...]]` em `content.xml` ou `styles.xml` | Reprocessar usando modelo executável SISGES ou modelo interno; conferir header/master-page | Bloqueia assinatura |
| `WARN_TEMPLATE_VISUAL_REFERENCE_ONLY` | ODT enviado é válido, mas não possui marcadores SISGES executáveis | Não usar diretamente; renderizar com modelo interno e tratar o ODT apenas como referência visual | Warning operacional; não deve gerar placeholder final |
| `ERR_TEMPLATE_NOT_EXECUTABLE` | ODT possui marcadores SISGES parciais ou inconsistentes | Corrigir o template para conter todos os marcadores SISGES obrigatórios | Bloqueia uso como template executável |
| `ERR_TEMPLATE_HEADER_MARKERS_UNSUPPORTED` | Marcadores executáveis foram encontrados em `styles.xml`/header, mas o renderizador ainda não substitui essa região com segurança | Mover marcadores para `content.xml` ou implementar substituição segura de header/master-page | Bloqueia uso direto do template |
| `ERR_QMS_RAW_LEAKED` | QMS bruto entrou no cabeçalho | Reprocessar após normalização; em caso individual usar `scripts.rebuild_folha_individual --force-qms "<valor>"` quando permitido | Documento parece mal gerado e pode induzir erro |
| `WARN_QMS_GENERICO` | SiCaPEx trouxe `QUALQUER QMG/QMP` | Conferir cadastro; se não houver valor confiável, manter vazio com warning | Pode seguir se a OM aceitar cabeçalho vazio |
| `WARN_QMS_NAO_RECONHECIDO` | QMS não bateu nas regras conhecidas | Corrigir cadastro ou usar hotfix individual com valor validado | Requer decisão humana |
| `ERR_MISSING_REQUIRED_MONTH` | Mês do semestre não foi renderizado | Reprocessar folha/lote | Bloqueia assinatura |
| `ERR_MONTH_DUPLICATED` | Mês apareceu mais de uma vez | Reagrupar eventos e reprocessar | Bloqueia assinatura |
| `WARN_MONTH_WITHOUT_EVENTS` | Mês sem evento | Não é erro se renderizado conforme padrão da OM | Informativo |
| `WARN_EVENT_TITLE_MISSING` | Parser não recuperou título | Revisar evento; se necessário corrigir fonte/variables e reprocessar | Pode exigir revisão manual |
| `WARN_TABLE_UNREPAIRED` | Tabela não foi reconstruída como tabela confiável | Revisar manualmente; corrigir tabela no ODT ou melhorar extração | Pode seguir apenas com ciência da secretaria |
| `WARN_TABLE_REPAIRED` | Tabela foi reconstruída automaticamente | Conferir visualmente | Risco médio |
| `ERR_ODT_INVALIDO` | ODT final não abre como ZIP/XML válido | Reprocessar folha | Bloqueia assinatura |
| `ERR_CONTENT_XML_INVALID` | `content.xml` não parseia | Reprocessar folha | Bloqueia assinatura |
| `WARN_PDF_PREVIEW_NOT_GENERATED` | LibreOffice/conversor indisponível | Gerar PDF em ambiente com LibreOffice ou conferir ODT | Pode seguir se PDF não for obrigatório |
| `ERR_TEMPO_CALCULO_FAILED` | Módulo de cálculo não conseguiu fechar a 2ª Parte | Corrigir dados de tempo/SiCaPEx e reprocessar | Bloqueia ou exige revisão humana formal |
| `WARN_TEMPO_PENDENTE_VALIDACAO` | Tempo gerado, mas exige conferência | Conferir 2ª Parte antes de assinar | Pode seguir com ciência, conforme decisão da secretaria |
| `HISTORICO_NAO_RECALCULADO` | 2ª Parte veio de transcrição histórica | Rodar cálculo real ou registrar ciência | Não tratar como cálculo homologado novo |
| `ERR_SIGNATURE_MISSING` | Assinatura ausente ou regra não aplicada | Reprocessar com regra oficial/praça correta | Bloqueia assinatura |
| Assinatura de oficial em folha de praça | Classificação falhou ou modelo fixo foi herdado | `python -m scripts.rebuild_folha_individual --identidade <id> --ano <ano> --semestre <semestre> --modelo data/input/modelos/MODELO_FOLHA.odt --output data/output/entrega_final/hotfix --force-assinatura-praca` | Bloqueia assinatura até conferência |
| Evento de pagamento/benefício filtrado | Regra documental excluiu evento indireto | Conferir justificativa; não corrigir se a regra estiver correta | Esperado quando documentado |
| Dry-run não gravou dados | Operador executou simulação | Reexecutar com `--commit` | Não há erro; apenas não persistiu |
| Commit com pendências | `--allow-pending-output` permitiu saída com warnings | Revisar relatórios e separar `REVISAR_MANUALMENTE` | Entrega controlada |

## Contrato de formatação

| Erro | Causa provável | Comando de correção | Impacto |
| --- | --- | --- | --- |
| `ERR_FORMAT_CONTRACT_NOT_APPLIED` | Renderizador gerou ODT fora do contrato visual configurado | `python -m scripts.validate_folha_format --odt <folha.odt> --contract <contract.json>` e reprocessar | Pode bloquear assinatura se afetar cabeçalho, meses, 2ª Parte ou assinatura |
| `WARN_EVENT_FILTERED_BY_POLICY` | Evento foi removido por regra de privacidade/escopo documental | Conferir `variables.filtered_events[]`; não reinserir sem decisão da secretaria | Esperado quando beneficiário/pagamento/terceiros forem filtrados |
| `WARN_POSSIBLE_SENSITIVE_EVENT` | Evento contém possível CPF, beneficiário, pagamento, arma, terceiro, conta bancária, SIGMA, PAF ou CRAF | Revisar antes da assinatura; não remover automaticamente sem política registrada | Pode seguir apenas com ciência/revisão humana |
| `WARN_REVIEW_BEFORE_SIGNATURE` | A validação encontrou conteúdo que exige conferência humana antes da assinatura | Abrir a folha, conferir a 1ª Parte e decidir manter, editar ou aplicar política futura | Requer atenção operacional |
| `WARN_TABLE_FILTERED_TO_MILITAR` | Tabela original continha terceiros e foi individualizada | Conferir se a linha do militar foi preservada | Pode seguir se a política estiver documentada |
| `OK_EMPTY_MONTH_COMPACT` | Mês vazio foi emitido como `DEZEMBRO: Sem Alteração.` | Nenhuma correção; modo compacto aceito pela configuração da OM | Informativo |
| `OK_HEADER_IN_STYLES_XML` | Cabeçalho foi localizado em header/master-page/styles.xml | Nenhuma correção | Evita falso erro quando o cabeçalho não está no corpo principal |

## Regra de ouro

Não corrigir silenciosamente. Todo hotfix deve gerar nova validação, preservar a versão anterior e deixar rastro no relatório.

Quando houver dúvida normativa, validar com a secretaria conforme norma vigente e modelo oficial adotado pela OM.
