# ADR 0001 — Contagem de tempo na janela do vínculo (Folhas de Alterações)

Status: aceita (2026-07-02)
Base normativa: EB30-N-10.002 (Port. 063-DGP/C Ex, 25 MAR 2020), Art. 20/21/24 e Anexo B.

## Contexto

O compilador de Folhas de Alterações calculava TC como semestre cheio
(`00a06m00d`) sempre que o período era um semestre-calendário, e ancorava o
TTES no fim do SEMESTRE, ignorando incorporação e desligamento. O Art. 20/21
determina que o vínculo com a OM começa no ato de inclusão e cessa no
desligamento — nenhum tempo pode ser contado fora da janela
`[incorporação, desligamento]`.

## Decisões

### 1. Dia do licenciamento NÃO conta (convenção exclusive)

Ato "a contar de 31 JAN 2024" ⇒ o último dia computável é 30 JAN 2024.
O dia da incorporação CONTA (inclusive).

- Alternativa rejeitada: contar também o dia do licenciamento (inclusive em
  ambas as pontas). Rejeitada porque "a contar de" marca o início da nova
  situação (licenciado); o militar não presta serviço na OM nesse dia.
- Impacto da escolha: ±1 dia no TC do último semestre. Decisão reversível em
  um único ponto: `Vinculo.ultimo_dia_computavel` em
  `modules/compilador/application/folha_time_calc.py`.

### 2. Semestre integral de vínculo vale 06m00d administrativos

Contagem administrativa (ano = 360 dias, mês = 30 dias, `format_admin_days`).
Semestre em que o vínculo cobre o período inteiro vale 180 dias
administrativos (06m00d), ainda que o semestre-calendário tenha 181–184 dias.
Janela parcial (incorporação/desligamento no meio do semestre) conta dia a
dia (`days_inclusive`).

### 3. TTES acumula (TC − TNC) semestre a semestre

`TTES(fim) = Σ por semestre [dias administrativos da janela efetiva − TNC]`,
do semestre da incorporação até `min(fim do vínculo, fim do período)`.
Exemplo (caso sintético de teste): incorporação 13 FEV 2023, licenciamento a
contar de 31 JAN 2024:

| Semestre | Janela efetiva | TC | TTES acumulado |
|---|---|---|---|
| 2023/1 | 13 FEV–30 JUN | 00a04m18d | 00a04m18d |
| 2023/2 | 01 JUL–31 DEZ | 00a06m00d | 00a10m18d |
| 2024/1 | 01 JAN–30 JAN | 00a01m00d | 00a11m18d |

- Alternativa rejeitada: TTES por diferença de calendário
  (`format_calendar_ymd(data_praça → fim)`). Rejeitada porque diverge da soma
  dos TC semestrais escriturados nas folhas anteriores (ex.: daria 10m19d em
  2023/2, quebrando a conciliação documental da transcrição).

### 4. TSCMM permanece aproximado de TTES — marcado

TSCMM tem regra própria (Port. 322-Cmt Ex, 2005) ainda não implementada.
O compilador segue emitindo TSCMM = TTES como aproximação, mas o
`TimeSummary` agora carrega `tscmm_origem="APROXIMADO_TTES"` (ou
`"TOTAIS_PART2"` quando transcrito do Part2Schema revisado) para que a
secretaria saiba que o valor exige conferência antes da assinatura.

### 5. Sem data de praça ⇒ tempos zerados

Sem âncora de vínculo o compilador NÃO assume semestre cheio: emite TC/TTES
zerados, forçando revisão humana (comportamento anterior mascarava o dado
faltante com `00a06m00d`).

## Ordem da 2ª Parte (Art. 24 / Anexo B)

Títulos escriturados SEMPRE, nesta ordem, mesmo zerados:
I-TC (a arregimentado, b não arregimentado, c trânsito, d instalação),
II-TNC, III-TSSD, IV-TSCMM, V-TSNR, VI-TTES.
O código anterior invertia TSSD e TSCMM; corrigido e travado por teste de
contrato (`test_ordem_segunda_parte_anexo_b`,
`test_segunda_parte_order_is_contractual`).
