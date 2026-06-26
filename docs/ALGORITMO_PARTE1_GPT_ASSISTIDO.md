# Algoritmo da 1ª Parte e GPT Assistido por Fontes

## 1. Objetivo

Este documento define a direção técnica do processamento da 1ª Parte das Folhas de Alterações no SISGES.

O objetivo não é fazer um GPT "escrever a folha". O objetivo é transformar uma fonte oficial de alterações em uma estrutura verificável:

```text
Alteracao(
  Parte1(
    Mes(
      Evento(
        Titulo,
        BI(Corpo)
      )
    )
  )
)
```

Essa estrutura deve ser gerada primeiro por algoritmo determinístico. Um modelo GPT pode auxiliar apenas em ambiguidades controladas, sempre devolvendo JSON dentro de esquema e sempre com validação posterior.

## 2. Fonte oficial preferencial

Quando disponível, o TXT oficial deve ser preferido ao PDF.

Motivo técnico:

- TXT reduz erro de OCR e extração visual.
- TXT preserva texto sem depender da geometria da página.
- TXT diminui ruído de cabeçalho, rodapé e quebra de linha.
- TXT é mais fácil de validar contra schema.
- TXT reduz superfície de ataque em comparação com parsing de PDF/ODT.

PDF continua sendo aceito como fonte alternativa, mas deve passar por limpeza de cabeçalho, normalização e validação.

## 3. Fontes explícitas e implícitas

### Fontes explícitas

São os arquivos entregues ao processo:

- TXT oficial de alterações;
- PDF de BI/alterações;
- ODT semi-pronto;
- modelo ODT;
- dados de militar no banco;
- contexto SiCaPEx;
- saída anterior da memória do Compilador.

Essas fontes dizem o que aconteceu.

### Fontes implícitas

São regras usadas para interpretar e validar:

- legislação e normas vigentes;
- modelo oficial adotado pela OM;
- contrato visual de formatação;
- política de privacidade e revisão;
- regras de cabeçalho, assinatura e tempo de serviço;
- regras de mês, BI, evento, tabela e conteúdo sensível.

Essas fontes dizem como interpretar, formatar e validar.

Quando houver dúvida normativa:

> Este ponto deve ser validado pela secretaria conforme norma vigente e modelo oficial adotado pela OM.

## 4. Camada determinística atual

O parser estrutural fica em:

```text
scripts/parse_parte1_events.py
```

Ele produz JSON no schema:

```text
sisges-parte1-events-v1
```

Cada evento fica assim:

```json
{
  "titulo": "INSTALAÇÃO - Concessão",
  "bi": {
    "referencia": "- a 1, BI Nº 50:",
    "corpo": "De acordo com o inciso..."
  },
  "warnings": []
}
```

Essa camada:

- identifica meses;
- identifica títulos;
- identifica referências de BI;
- une corpo quebrado em linhas;
- preserva itens numerados como corpo;
- preserva rótulos de tabela como corpo;
- preenche meses ausentes com "Sem alterações.";
- emite warnings para conteúdo sensível;
- não remove conteúdo automaticamente.

## 5. Papel do GPT

O GPT pode entrar como assistente de interpretação, não como autoridade final.

Uso permitido:

- sugerir divisão de evento quando o parser sinalizar ambiguidade;
- classificar título, referência e corpo em JSON;
- explicar motivo de uma pendência;
- sugerir warning operacional;
- comparar saída estruturada com fonte explícita.

Uso proibido:

- inventar evento;
- completar BI inexistente;
- alterar tempo de serviço;
- remover conteúdo sem política e registro;
- decidir assinatura;
- substituir validação normativa da secretaria.

## 6. Proteção contra entrada maliciosa

Todo input documental deve ser tratado como dado não confiável.

Medidas necessárias:

- nunca executar conteúdo de TXT/PDF/ODT;
- nunca montar SQL a partir de texto de documento;
- usar parser e schema antes de persistir;
- registrar hash da fonte;
- validar extensão e conteúdo real do arquivo;
- gerar warnings para conteúdo sensível;
- separar fonte de alterações de modelo ODT;
- manter JSON intermediário auditável.

Isso reduz risco de injeção, confusão de papel documental e erro silencioso.

## 7. Próximo corte técnico

O próximo passo recomendado é conectar este JSON estrutural ao renderizador de Parte 1.

Fluxo desejado:

```text
TXT/PDF oficial
  -> parse_parte1_events
  -> parte1_events.json
  -> validação estrutural
  -> renderizador ODT
  -> validação visual/formal
```

Depois disso, o GPT assistido pode atuar apenas entre parser e validação:

```text
parser determinístico
  -> pendência/ambiguidade
  -> GPT restrito por schema
  -> JSON sugerido
  -> validador determinístico
  -> operador decide
```

## 8. Evidência atual

O parser foi validado com testes unitários e com TXT real de alterações.

Resultado técnico esperado:

- meses reconhecidos;
- eventos reconhecidos;
- BI e corpo aninhados;
- ausência de eventos falsos por linha de tabela;
- ausência de eventos falsos por item numerado;
- warnings sensíveis sem remoção automática.

Os JSONs de experimento devem permanecer em `data/output/experimentos/` e não devem ser versionados.
