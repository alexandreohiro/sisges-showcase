# Contrato de Formatacao da Folha - Referencia Visual

## 1. Classificacao do Caso

O arquivo `REFERENCIA_VISUAL_ODT` deve ser tratado como fixture visual de formatacao da Folha de Alteracoes. Ele nao e pacote final auditavel, nao substitui `variables.json`, nao prova origem dos dados e nao deve ser usado como verdade fixa de assinatura, calculo de tempo ou filtragem de eventos.

Ele tambem nao deve ser tratado como template executavel do SISGES apenas por ser um ODT bem formatado. Template executavel precisa conter marcadores proprios do Compilador:

- `[[SISGES:HEADER]]`
- `[[SISGES:PRIMEIRA_PARTE]]`
- `[[SISGES:COMPORTAMENTO]]`
- `[[SISGES:SEGUNDA_PARTE]]`
- `[[SISGES:ASSINATURA]]`

ODT sem esses marcadores e referencia visual. O Compilador pode usar sua aparencia como contrato, mas deve renderizar a folha pelo modelo interno seguro ou por outro template executavel. Nenhum output final pode sair com `[GRADUACAO]`, `[NOME]`, `[PERIODO]`, `{{...}}` ou `[[SISGES:...]]`.

Neste contexto:

- o PDF de alteracoes e fonte bruta dos eventos;
- o SiCaPEx e fonte de dados pessoais, QMS, comportamento e tempo;
- o ODT de referencia visual e referencia de layout, estrutura, estilos e nuances visuais;
- o Compilador deve reproduzir o padrao formal, mantendo rastreabilidade propria.

## 2. Decisoes Operacionais Observadas

A ausencia de `Declaracao de Beneficiario` no ODT final de referencia nao deve ser tratada automaticamente como erro. Esse tipo de item pode representar informacao indireta de pagamento, beneficiario, terceiros ou dado sensivel. A politica correta e registrar filtragem futura em `variables.filtered_events[]`, com motivo, origem e regra aplicada.

A tabela de ferias pode ser individualizada para preservar apenas a linha do militar quando a fonte trouxer terceiros. Essa reducao deve registrar `table_policy`, por exemplo `FILTERED_TO_MILITAR`.

O mes vazio em modo compacto e aceito para a OM quando configurado:

```text
DEZEMBRO: Sem Alteracao.
```

Isso e diferente do modo em bloco:

```text
DEZEMBRO:
Sem alteracoes.
```

`COMPACT_SINGULAR` e modo aceito, nao obrigatorio. Outras OMs podem usar `BLOCK` ou `COMPACT_PLURAL` por configuracao.

## 3. O Que Deve Ser Extraido Como Contrato Visual

O foco principal do ODT de referencia visual e:

- fonte;
- espacamento;
- margens;
- cabecalhos;
- continuacao;
- mes sublinhado;
- titulo;
- referencia de BI;
- corpo;
- tabelas;
- comportamento;
- 2a Parte;
- assinatura;
- estilos ODT.

## 4. Assinatura

A assinatura presente no ODT de referencia visual deve ser lida como placeholder ou flag visual. O validador de formatacao deve confirmar bloco, posicao e centralizacao. A definicao nominal da autoridade continua sendo variavel operacional do Compilador, validada por regras separadas.

## 5. Cabecalho

O cabecalho pode estar em `content.xml`, `styles.xml`, `master-page` ou `header`. O validador nao deve acusar ausencia se a estrutura estiver presente em `styles.xml`.

Regras visuais esperadas:

- nome completo preservado;
- apenas nome de guerra em negrito;
- graduacao sem negrito;
- QMS limpo e sem valor bruto;
- identidade sem negrito;
- periodo claro.

## 6. Politica Futura de Filtragem

Beneficiario, pagamento e terceiros podem ser filtrados por politica de privacidade da OM. TAF, ferias, promocao, curso, sindicancia e convalescenca permanecem por padrao, salvo decisao manual.

No estado operacional atual, essa politica existe como base de classificacao e auditoria, mas nao deve remover eventos automaticamente em producao. A flag padrao e desligada: `COMPILADOR_PARTE1_FILTER_POLICY_ENABLED = false`.

Nesta fase, conteudo sensivel detectado na fonte gera warning, nao remocao automatica. Exemplos: CPF, endereco, filiacao, arma de fogo, beneficiario, pagamento, dados de terceiros, conta bancaria, SIGMA, PAF e CRAF. Os codigos esperados sao `WARN_POSSIBLE_SENSITIVE_EVENT` e `WARN_REVIEW_BEFORE_SIGNATURE`.

Se a OM decidir aplicar filtro, cada remocao precisa ser explicita, rastreada e registrada em `variables.filtered_events[]`. Sem esse registro, a politica nao deve ser aplicada em lote.

Todo evento removido deve gerar registro tecnico:

```json
{
  "titulo": "DECLARACAO DE BENEFICIARIO - Atualizacao",
  "reason": "EVENTO_BENEFICIARIO_PRIVACIDADE",
  "source_bi": "BI No 84",
  "policy": "OM_PRIVACY_FILTER_V1",
  "policy_code": "OM_PRIVACY_FILTER_V1"
}
```

Portanto, a ausencia de conteudo no ODT manual de referencia visual pode representar decisao operacional humana, nao uma regra universal do Compilador. O contrato visual nao autoriza filtro silencioso.

## 7. Conclusao

O ODT de referencia visual e contrato visual, nao fonte normativa absoluta. Ele orienta como a Folha deve parecer. O SISGES continua responsavel por separar fonte, calculo, renderizacao, validacao e auditoria.

Pontos normativos e decisoes de privacidade devem ser validados pela secretaria conforme norma vigente e modelo oficial adotado pela OM.

A release congelada das folhas revisadas permanece fora deste contrato de desenvolvimento. Qualquer alteracao futura na politica semantica de eventos deve gerar nova execucao, novo pacote, novo hash e nova validacao operacional.

