# Algoritmo Assistido — ODT Semi OK + PDF Parte 1

Este fluxo atende pastas legadas em que a Folha de Alteracoes ja existe como ODT semi pronto, normalmente com sufixo `o`, mas ainda sem a 1a Parte preenchida. O PDF correspondente fornece a 1a Parte do semestre.

O objetivo nao e gerar a folha do zero. O objetivo e completar o ODT semi OK preservando cabecalho, 2a Parte, assinatura e demais estrutura ja existente.

## Quando Usar

Use este fluxo quando:

- o ODT ja tem estrutura individual do militar;
- a 2a Parte ja esta montada ou transcrita;
- a 1a Parte esta disponivel em PDF;
- o operador precisa completar lote legado sem refazer toda a compilacao.

Nao use este fluxo como substituto do Compilador completo quando o banco, calculo de tempo e fontes ja estiverem estruturados para geracao integral.

## Comando

```bash
python -m scripts.complete_folha_semi_ok_parte1 \
  --input "CAMINHO_DA_PASTA_LEGADA" \
  --output data/output/semi_ok_parte1_saida \
  --semestre 2
```

## Endpoint Operacional

O mesmo fluxo pode ser acionado por usuário em modo dev:

```http
POST /documents/folhas/semi-ok-parte1/process
```

Payload:

```json
{
  "input_dir": "CAMINHO_DA_PASTA_LEGADA",
  "output_dir": "semi_ok_parte1_saida",
  "semestre": "2"
}
```

Regras de segurança:

- exige usuário autenticado em modo dev;
- a pasta de entrada deve existir;
- a pasta de saída sempre deve ficar dentro de `data/output`;
- a pasta original não é alterada.

## O Que o Script Faz

1. Classifica arquivos da pasta:
   - `MODELO_ODT`;
   - `ODT_OK_REFERENCIA`;
   - `ODT_SEMI_OK`;
   - `PDF_PARTE1`.
2. Faz pareamento por nome normalizado.
3. Extrai a Parte 1 do PDF, começando no primeiro mes do semestre.
4. Remove cabecalhos de continuacao do PDF.
5. Remove caracteres invalidos para XML.
6. Abre o ODT semi OK como pacote ODT.
7. Localiza os marcadores `1a PARTE` e `2a PARTE`.
8. Substitui o espaco vazio entre esses marcadores pela Parte 1 extraida.
9. Valida o ODT gerado.
10. Gera CSV, JSON, trace individual e relatorio.

## Saidas

A pasta de saida recebe:

- `*_parte1_experimental.odt`;
- `*_parte1_limpa.txt`;
- `*_validacao.json`;
- `*_trace.json`;
- `matriz_pares_semi_ok.csv`;
- `resumo_lote_semi_ok_parte1.csv`;
- `resumo_lote_semi_ok_parte1.json`;
- `RELATORIO_LOTE_SEMI_OK_PARTE1.txt`.

## Status

- `OK`: estrutura valida, sem warning.
- `OK_WITH_WARNINGS`: ODT valido, mas exige conferencia humana.
- `ERROR`: ODT ou pareamento bloqueado.

## Warnings Esperados

`OK_WITH_WARNINGS` nao significa falha. Em lote legado, ele normalmente indica:

- possivel conteudo sensivel;
- referencia a pagamento, contracheque ou SIPPES;
- tabela extraida como texto;
- necessidade de revisao visual antes de assinatura.

## Regra Operacional

O script nunca altera a pasta original. Toda saida deve ficar em `data/output/` ou pasta equivalente fora do Git.

Antes de assinatura, abrir os ODTs gerados visualmente no LibreOffice e conferir:

- meses;
- titulos de eventos;
- referencias de BI;
- tabelas;
- 2a Parte;
- assinatura;
- conteudo sensivel.
