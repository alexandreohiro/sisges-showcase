# Algoritmo Folha de Alterações — Modelo ODT + PDF

## Objetivo

Este fluxo transforma um modelo ou base ODT de Folha de Alterações em um ODT preenchido com a 1ª Parte extraída de um PDF de alterações/BI.

Ele existe para o caso operacional em que a secretaria já possui:

- um ODT base, modelo ou semi-pronto;
- um PDF com as alterações do semestre;
- uma referência visual/manual `ok`, quando disponível.

## Entrada

- `modelo_odt`: ODT modelo, base ou semi-pronto.
- `fonte_pdf`: PDF da 1ª Parte.
- `reference_odt`: ODT `ok` opcional, usado apenas para comparação.
- `semestre`: `1` ou `2`.

## Saída

O comando gera, em uma pasta de saída fora do Git:

- ODT final experimental;
- `parte1_normalizada.txt`;
- `validacao_modelo_pdf.json`;
- `comparacao_referencia.json`;
- `resultado_modelo_pdf.json`;
- `RELATORIO_MODELO_PDF_ALGORITMO.txt`.

## Comando

```bash
python -m scripts.render_folha_modelo_pdf \
  --modelo data/output/experimento_moraes_algoritmo/000_MODELO.odt \
  --pdf data/output/experimento_moraes_algoritmo/fonte_moraes.pdf \
  --reference-odt data/output/experimento_moraes_algoritmo/referencia_moraes_ok.odt \
  --output data/output/experimento_moraes_algoritmo \
  --semestre 2
```

## Como o algoritmo funciona

1. Extrai texto do PDF.
2. Localiza a região da 1ª Parte pelos meses do semestre.
3. Remove cabeçalhos e rodapés de página.
4. Limpa caracteres inválidos para XML.
5. Detecta conteúdo potencialmente sensível.
6. Normaliza linhas físicas do PDF em parágrafos documentais.
7. Preserva mês, título e referência BI como blocos separados.
8. Injeta a 1ª Parte entre os marcadores `1ª PARTE` e `2ª PARTE` do ODT.
9. Valida o ODT gerado.
10. Compara com ODT `ok`, se informado.

## Modelo ODT executavel SISGES

O modelo operacional recomendado nao e um ODT manual qualquer. Ele deve ser um ODT executavel do SISGES, com flags explicitas para o renderer preencher sem adivinhacao.

Flags atualmente aceitas:

- `[SISGES_NOME]`;
- `[SISGES_GRADUACAO]`;
- `[SISGES_QMS]`;
- `[SISGES_IDENTIDADE]`;
- `[SISGES_SEMESTRE_TEXTO]`;
- `[SISGES_PERIODO]`;
- `[SISGES_POSTO_GRADUACAO_CONTINUACAO]`;
- `[SISGES_PARTE_1]`;
- `[SISGES_COMPORTAMENTO]`;
- `[SISGES_DATA_LOCAL]`;
- `[SISGES_ASSINATURA_NOME]`;
- `[SISGES_ASSINATURA_FUNCAO]`.

O cabecalho pode ficar em `styles.xml`, `master-page` ou `header`. Nesse caso, o renderer deve preencher `styles.xml` tambem, nao apenas `content.xml`.

Se o ODT nao tiver flags SISGES, ele deve ser tratado como referencia visual ou fonte de alteracoes, nao como template executavel. O fallback entre `1Âª PARTE` e `2Âª PARTE` continua existindo para lote legado, mas nao e o caminho preferencial para novos modelos.

Modelo gerado nesta etapa:

- `data/output/modelos/000_MODELO_SISGES_EXECUTAVEL_V1.odt`;
- copia operacional local: `C:\caminho\para\MODELO_SISGES_EXECUTAVEL_V1.odt`.

## Regras importantes

- PDF de alterações alimenta a 1ª Parte.
- PDF de alterações não é fonte primária para cálculo de tempo.
- ODT `ok` é referência visual/formal, não regra universal de filtragem.
- Conteúdo sensível não é removido automaticamente.
- Conteúdo sensível gera warning e exige revisão antes da assinatura.
- Placeholder restante bloqueia a entrega.
- QMS bruto não pode vazar.

## Limite técnico

O algoritmo consegue chegar a uma folha estruturalmente válida usando modelo ODT e PDF. Para equivalência completa com um ODT `ok`, o sistema ainda precisa combinar:

- dados pessoais do banco/Gestão de Pessoal;
- tempo de serviço do módulo de cálculo;
- assinatura conforme regra operacional;
- política explícita da OM para conteúdo sensível;
- eventual ODT semi-pronto quando a secretaria já tiver 2ª Parte validada.

## Caso MORAES

O caso MORAES demonstrou que o fluxo consegue:

- usar cópia do `000 MODELO.odt`;
- usar cópia do PDF de alterações;
- gerar ODT válido;
- preservar todos os meses do 2º semestre;
- remover cabeçalhos/rodapés de página;
- normalizar centenas de linhas do PDF em parágrafos documentais;
- emitir warnings de conteúdo sensível.

A comparação também mostrou que um ODT `ok` pode preservar conteúdo sensível. Portanto, `ok` visual não significa sanitização semântica. A decisão de remover ou manter eventos deve ser política explícita da OM e precisa ficar rastreada.
