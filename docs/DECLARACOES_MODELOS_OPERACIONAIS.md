# Declaracoes - Modelos Operacionais

Este documento registra o fluxo seguro para transformar ODTs reais da pasta da secretaria em modelos preenchiveis pelo SISGES.

## Regra operacional

Os ODTs originais da pasta `006 - DECLARACOES` sao tratados como referencia visual.

O SISGES nao altera esses arquivos. Quando um modelo precisa ser usado pelo Compilador, o sistema cria uma copia local com flags `[]` em `data/input/modelos/declaracoes`.

## Comando de preparacao

```powershell
cd C:\caminho\para\sisges
.\.venv\Scripts\python.exe -m scripts.prepare_declaracao_templates --overwrite
```

## Preparacao pela interface

A tela de Declaracoes tambem possui a acao `Preparar modelos`.

Essa acao chama:

```text
POST /declaracoes/modelos/preparar
```

O endpoint usa a pasta de origem configurada para a secretaria, cria copias gerenciadas em `data/input/modelos/declaracoes`, atualiza o relatorio local e recarrega o catalogo de modelos preenchiveis.

## Saidas locais

- `data/input/modelos/declaracoes/**/*.odt`
- `data/output/declaracao_templates_preparados.json`

Essas saidas sao operacionais locais e nao devem ser commitadas.

## Estado observado

- 13 ODTs candidatos processados.
- 13 copias com flags SISGES geradas.
- O catalogo passou a listar 13 modelos preenchiveis e 13 referencias visuais preservadas.

## Validacao

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_documento_compiler.py
.\.venv\Scripts\python.exe -m ruff check .
```

## Observacao

O preparador de modelos e uma etapa assistida. Ele reduz retrabalho, mas a secretaria ainda deve abrir visualmente os modelos gerados antes de uso amplo para confirmar texto, assinatura, destino e campos variaveis.
