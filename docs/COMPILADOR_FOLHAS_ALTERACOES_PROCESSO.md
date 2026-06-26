# Compilador de Folhas de Alterações — Processo Operacional SISGES

## 1. A dor que o processo resolve

A secretaria não monta uma Folha de Alterações a partir de uma única tela limpa. Ela recebe fontes espalhadas: Fichas SiCaPEx, PDFs de BI, PDFs de folhas anteriores, documentos de alteração, histórico do militar, cálculo de tempo, modelo ODT oficial e regras internas de assinatura. Cada militar tem trajetória própria. Cada semestre precisa ser fechado. Quando há semestres acumulados, o problema deixa de ser apenas "digitar uma folha" e passa a ser controlar uma linha de produção documental.

O erro típico não é só erro de digitação. O erro real é mais perigoso:

- mês ausente;
- mês duplicado;
- dado de outro militar dentro da folha;
- título colado no corpo;
- referência de BI perdida;
- QMS bruto no cabeçalho;
- data de nascimento confundida com data de praça;
- tempo de serviço inconsistente;
- tabela quebrada como texto desalinhado;
- assinatura errada;
- modelo ODT ignorado;
- PDF gerado sem o mesmo conteúdo do ODT;
- arquivo final sem rastro de origem.

A Folha de Alterações é documento de histórico funcional. Se for feita de forma frágil, o problema aparece depois: na conferência, na assinatura, na contagem de tempo, na auditoria ou na reconstrução do histórico do militar.

O Compilador existe para transformar uma atividade manual, repetitiva e sujeita a erro oculto em uma cadeia rastreável:

```text
fonte → extração → normalização → cálculo → renderização → validação → pacote final
```

Ele não substitui a secretaria. Ele reduz retrabalho, expõe pendências e força o documento a nascer com memória, justificativa e validação.

## 2. O que é uma Folha de Alterações dentro do SISGES

Dentro do SISGES, a Folha de Alterações é tratada como um documento semestral de histórico funcional do militar. Ela consolida o que foi registrado ou publicado no período e organiza esse conteúdo em forma oficial.

Ela contém:

- cabeçalho de identificação do militar;
- 1ª Parte, com alterações do semestre;
- comportamento;
- 2ª Parte, com tempo de serviço;
- assinatura da autoridade responsável;
- formatação conforme modelo documental oficial da OM.

Não é apenas relatório. É peça de histórico funcional. Por isso, o sistema precisa preservar origem, datas, fontes, cálculos, validações e arquivos finais.

## 3. Por que não é CRUD

CRUD salva campos. Compilar Folha exige interpretar, decidir, cruzar e provar.

Uma tela de cadastro comum consegue gravar:

```text
nome
identidade
graduação
observação
```

O Compilador precisa fazer muito mais:

- interpretar PDFs;
- associar eventos ao militar correto;
- agrupar por mês e semestre;
- preservar ordem cronológica;
- diferenciar título, referência e corpo;
- detectar linhas de BI;
- preservar tabelas;
- excluir eventos que não pertencem à folha final;
- aplicar modelo ODT oficial;
- calcular ou consolidar tempo de serviço;
- validar assinatura;
- gerar ODT, PDF, TXT e ZIP;
- registrar memória e auditoria.

Conclusão operacional: o Compilador é um motor documental, não uma tela de cadastro.

## 4. Entradas do processo

### 4.1 SiCaPEx

O SiCaPEx alimenta a base estrutural do militar. Ele é usado para:

- nome completo;
- nome de guerra;
- posto/graduação;
- identidade;
- Prec-CP;
- QAS/QMS/QM;
- data de praça;
- OM;
- comportamento;
- movimentações;
- afastamentos;
- descontos;
- acréscimos;
- base de cálculo de tempo.

Riscos conhecidos:

- data de nascimento pode ser capturada no lugar de data de praça se o parser for global e frouxo;
- QMS pode vir genérico, como `QUALQUER QMG / QUALQUER QMP`;
- OM pode vir com ruído textual;
- nome de guerra pode ser contaminado por referência de BI;
- dados sensíveis não devem aparecer em relatório aberto.

Regra operacional implementada no SISGES: dado sensível não deve ser tratado como texto livre de log. O relatório operacional deve mostrar apenas o necessário para identificação administrativa.

Pendência de validação normativa: a secretaria deve confirmar, conforme norma vigente e modelo oficial adotado pela OM, quais campos do SiCaPEx podem ser transcritos na Folha e quais devem ficar apenas como fonte de auditoria.

### 4.2 PDFs de alterações, BI e fontes do período

Esses PDFs alimentam a 1ª Parte. Eles fornecem:

- eventos;
- títulos;
- referências de BI;
- corpo textual;
- tabelas;
- meses;
- publicações.

Riscos:

- cabeçalho de página pode se misturar ao corpo;
- título pode ficar vazio;
- título pode grudar no corpo;
- tabela pode virar texto desalinhado;
- evento pode ser associado ao militar errado;
- evento indireto pode aparecer na fonte, mas não pertencer à folha final.

Exemplo operacional: um evento de declaração de beneficiário pode constar no PDF fonte, mas ser filtrado por regra documental por tratar de informação indireta de pagamento/benefício pessoal. Nesse caso, a ausência no ODT final não é perda: é exclusão controlada. A justificativa ou validação deve indicar que houve filtro por regra documental quando isso for relevante para conferência.

### 4.3 Modelo ODT oficial

O modelo ODT é a forma oficial do documento. Ele define:

- formatação;
- estilos;
- fonte;
- cabeçalho;
- tabelas;
- espaçamento;
- estrutura da 1ª e 2ª Parte;
- assinatura;
- aparência final esperada.

Regra operacional implementada no SISGES: se um modelo ODT foi informado, ele deve ser usado. O sistema não pode cair silenciosamente para template interno.

O modelo analisado usa placeholders como:

```text
[NOME_FORMATADO]
[NOME_GUERRA]
[GRADUACAO]
[QM]
[IDENTIDADE]
[PERIODO]
[PARTE1]
[TC]
[TNC]
[TTES]
```

Alguns campos podem estar em `content.xml`; outros podem estar em `styles.xml`, especialmente no cabeçalho. Portanto, o renderizador precisa substituir ambos.

### 4.4 Banco SISGES

O banco é o contexto consolidado. Ele guarda:

- cadastro do militar;
- ficha SiCaPEx importada;
- períodos de serviço;
- eventos funcionais;
- documentos gerados;
- memória documental;
- execuções do Compilador;
- validações;
- hashes;
- outputs.

O banco evita que o Compilador dependa apenas da transcrição do PDF. Se o PDF traz QMS genérico, mas o banco possui QMS normalizado, o cabeçalho deve usar o valor consolidado e registrar a decisão.

### 4.5 Memória do Compilador

A memória do Compilador preserva tudo que entra e sai:

- PDF SiCaPEx;
- PDF de alteração;
- ODT modelo;
- ODT final;
- PDF final;
- TXT de validação;
- TXT de justificativa;
- `variables.json`;
- ZIP individual;
- pacote geral.

Cada arquivo deve ter:

- caminho de armazenamento;
- hash SHA-256;
- papel no processo;
- vínculo com execução;
- vínculo com militar, quando possível.

Isso permite reprocessar, auditar, comparar versões e corrigir uma folha sem recomeçar o lote inteiro.

## 5. Pipeline geral de compilação

Fluxo operacional:

1. Receber fontes.
2. Salvar inputs na memória.
3. Calcular hash.
4. Extrair texto e estrutura.
5. Identificar militar.
6. Normalizar dados.
7. Extrair eventos.
8. Associar eventos ao militar.
9. Agrupar por semestre e mês.
10. Montar a 1ª Parte.
11. Construir contexto de tempo.
12. Calcular ou consolidar a 2ª Parte.
13. Aplicar modelo ODT.
14. Gerar ODT.
15. Gerar PDF.
16. Gerar validação.
17. Gerar justificativa.
18. Gerar pacote individual.
19. Gerar pacote geral.
20. Classificar como pronta, revisar ou bloqueada.

Diagrama:

```text
SiCaPEx + PDFs de alterações + modelo ODT
        ↓
Importadores
        ↓
Banco + Memória do Compilador
        ↓
Normalização e Associação
        ↓
Cálculo de tempo
        ↓
Renderização ODT
        ↓
Validação
        ↓
PDF/ZIP/Relatórios
```

## 6. Cabeçalho da Folha

O cabeçalho identifica formalmente o militar. Ele deve ser limpo, consistente e sem vazamento de dado bruto.

Regras:

- nome deve conter o nome completo;
- apenas o nome de guerra deve aparecer em negrito quando o modelo usa nome formatado;
- graduação não deve ficar em negrito como se fosse destaque solto;
- QAS/QMS/QM não deve ficar em negrito como dado especial;
- identidade não deve ficar em negrito;
- período deve estar claro.

Normalização de QMS/QM:

- `QUALQUER QMG / QUALQUER QMP` não deve aparecer;
- `QMG 00-QUALQUER QMG` deve virar vazio com warning;
- `MATERIAL BÉLICO/MANUTENÇÃO DE VIATURA AUTO` deve virar `MATERIAL BÉLICO`;
- `5310 - QMS - INTENDÊNCIA` deve virar `INTENDÊNCIA`;
- `INFANTARIA` permanece `INFANTARIA`;
- `COMUNICAÇÕES` permanece `COMUNICAÇÕES`.

Por que isso importa: o cabeçalho é a primeira prova de qualidade do documento. Se aparece `QUALQUER QMG` ou código bruto, o operador perde confiança no restante, mesmo que a 1ª Parte esteja correta.

## 7. 1ª Parte — alterações do semestre

A 1ª Parte é a narrativa administrativa do semestre. Ela mostra, mês a mês, os fatos publicados ou registrados que pertencem à Folha.

Ela deve conter:

- meses obrigatórios;
- eventos organizados;
- título;
- referência de BI;
- corpo;
- tabelas quando existirem.

Meses do 1º semestre:

- JANEIRO
- FEVEREIRO
- MARÇO
- ABRIL
- MAIO
- JUNHO

Meses do 2º semestre:

- JULHO
- AGOSTO
- SETEMBRO
- OUTUBRO
- NOVEMBRO
- DEZEMBRO

Cada mês aparece uma única vez.

Regra visual: o mês, incluindo os dois pontos, deve aparecer como marcador estrutural sublinhado:

```text
JANEIRO:
DEZEMBRO:
```

Quando não houver alteração, existem dois padrões aceitos conforme o modelo da OM:

```text
DEZEMBRO:
Sem alterações.
```

ou, quando o modelo consolidado da OM usa formato compacto:

```text
DEZEMBRO: Sem Alteração.
```

Esse ponto deve ser validado pela secretaria conforme norma vigente e modelo oficial adotado pela OM. No SISGES, a regra precisa ser explícita: se o formato compacto for adotado, não deve ser tratado como erro; deve ser tratado como padrão documental configurado.

Erros que a regra evita:

- mês faltando;
- mês duplicado;
- evento fora do mês;
- texto de outro militar dentro da folha;
- cabeçalho do PDF tratado como alteração;
- mês sem evento parecendo esquecido.

## 8. Título, referência e corpo

A 1ª Parte deve preservar três peças:

Título: assunto da alteração.

```text
TESTE DE AVALIAÇÃO FÍSICA - Resultado
```

Referência: linha que aponta a publicação.

```text
- a 20, BI Nº 64 :
```

Corpo: descrição do fato administrativo.

Erro crítico de legibilidade: quando o título fica vazio e aparece colado ao corpo, a folha fica difícil de conferir. O operador passa a precisar reler o bloco inteiro para descobrir o assunto.

Regra operacional implementada no SISGES: o Compilador deve tentar recuperar título pela linha anterior à referência, por estilo de negrito, caixa alta ou padrão de título. Se não conseguir, deve preservar o corpo e gerar:

```text
WARN_EVENT_TITLE_MISSING
```

Observação prática: alguns documentos finais podem manter referência e corpo no mesmo parágrafo por padrão visual do modelo. Isso não é necessariamente erro se a legibilidade estiver preservada, mas o `variables.json` deve guardar título, referência e corpo de forma separada para auditoria e reprocessamento.

## 9. Tabelas dentro das alterações

Algumas alterações têm tabelas:

- equipes;
- designações;
- fiscais;
- comissões;
- relação de militares;
- plano de férias;
- resultados.

Regra: tabela deve permanecer tabela. Não pode virar texto quebrado, desalinhado e impossível de conferir.

Se não for possível reconstruir perfeitamente:

- preservar conteúdo;
- marcar `WARN_TABLE_UNREPAIRED`;
- enviar para revisão manual;
- não esconder o problema.

Uma tabela com quantidade irregular de células por linha pode abrir visualmente aceitável, mas deve ser marcada para conferência porque indica reparo parcial.

## 10. Comportamento

O comportamento entra como informação destacada após a 1ª Parte.

Formato:

```text
Comportamento: EXCEPCIONAL
```

Apenas o tipo deve ficar em negrito:

- BOM
- ÓTIMO
- EXCEPCIONAL
- INSUFICIENTE

Se não encontrado:

- deixar pendência;
- não inventar;
- registrar no TXT de validação.

## 11. 2ª Parte — tempo de serviço

A 2ª Parte não é texto comum. É fechamento de tempo.

Campos:

- Tempo Computado de Efetivo Serviço (TC);
- Arregimentado;
- Não Arregimentado;
- Tempo Não Computado (TNC);
- Tempo de Serviço Computável para Medalha Militar (TSCMM);
- Tempo de Serviço em Situações Diversas (TSSD), quando aplicável;
- Tempo de Serviço Nacional Relevante (TSNR);
- Tempo Total de Efetivo Serviço (TTES).

Fontes:

- o SiCaPEx alimenta dados de base;
- o banco consolida o contexto do militar;
- o módulo de cálculo de tempo deve calcular ou estruturar o fechamento;
- PDF antigo de folha pode ser histórico/transcrição, mas não deve ser automaticamente tratado como cálculo novo.

Regra operacional:

```text
HISTORICO_NAO_RECALCULADO
```

quando a 2ª Parte vem de transcrição de PDF anterior.

```text
CALCULADO_SICAPEX_DB
```

ou equivalente quando o módulo de cálculo usa dados importados do banco.

```text
PENDENTE_VALIDACAO_HUMANA
```

quando há dado suficiente para montar a folha, mas a secretaria precisa conferir.

A dor é alta: tempo de serviço errado afeta histórico, medalha, contagem administrativa e confiança documental. Este ponto deve ser validado pela secretaria conforme norma vigente e modelo oficial adotado pela OM.

## 12. Modelo ODT oficial

O modelo ODT é a pele formal do documento. Sem ele, o sistema pode até gerar texto correto, mas parecer errado.

Regras:

- preservar `styles.xml`;
- preservar `content.xml` quando possível;
- substituir placeholders em `content.xml` e `styles.xml`;
- usar placeholders ou anchors;
- não ignorar modelo;
- validar uso do modelo;
- bloquear fallback silencioso.

Regra de segurança de template:

- ODT de referência visual não é automaticamente template executável.
- Para ser executável, o ODT precisa conter os marcadores SISGES:
  `[[SISGES:HEADER]]`, `[[SISGES:PRIMEIRA_PARTE]]`, `[[SISGES:COMPORTAMENTO]]`, `[[SISGES:SEGUNDA_PARTE]]` e `[[SISGES:ASSINATURA]]`.
- ODT válido sem esses marcadores deve ser classificado como `VISUAL_REFERENCE_ONLY`.
- ODT visual sem marcadores não deve ser usado diretamente para renderização; o Compilador usa o modelo interno seguro e registra `WARN_TEMPLATE_VISUAL_REFERENCE_ONLY`.
- Se sobrar `[GRADUACAO]`, `[NOME]`, `[PERIODO]`, `{{...}}` ou `[[SISGES:...]]` no ODT final, a validação gera `ERR_TEMPLATE_PLACEHOLDER_LEFTOVER`.
- Placeholder restante é erro crítico porque indica que o cabeçalho, rodapé, master-page ou corpo não foram dominados pelo renderizador.

Códigos:

- `OK_TEMPLATE_USED`
- `OK_TEMPLATE_EXECUTABLE`
- `WARN_TEMPLATE_VISUAL_REFERENCE_ONLY`
- `ERR_TEMPLATE_NOT_EXECUTABLE`
- `ERR_TEMPLATE_PLACEHOLDER_LEFTOVER`
- `ERR_TEMPLATE_IGNORED`
- `ERR_TEMPLATE_ANCHOR_NOT_FOUND`
- `OK_STYLES_PRESERVED`
- `ERR_TEMPLATE_PLACEHOLDER_UNRESOLVED`

Se o modelo foi enviado e o sistema ignora, isso é erro crítico, não warning.

## 13. Assinatura

Regra operacional implementada:

Praças:

```text
SIGNATARIO PRACA - Cel
S Cmt B Adm QGEx
```

Oficiais:

```text
SIGNATARIO OFICIAL - Cel
Cmt B Adm QGEx
```

A assinatura deve estar centralizada.

Se o sistema não souber classificar oficial/praça:

- marcar pendência;
- não inventar;
- enviar para revisão manual.

Este ponto deve ser validado pela secretaria conforme norma vigente e modelo oficial adotado pela OM.

## 14. Saídas por militar

Cada militar deve gerar uma pasta individual:

- `compiler_run.json`
- `folha_alteracoes.odt`
- `parte_1_alteracoes.odt`
- `folha_alteracoes.pdf`
- `validacao.txt`
- `justificativa.txt`
- `variables.json`
- `pacote.zip`

Função de cada arquivo:

`compiler_run.json`: histórico técnico da execução, status, fontes, período, warnings, errors e outputs.

`folha_alteracoes.odt`: documento editável.

`parte_1_alteracoes.odt`: recorte editável e formatado da 1ª Parte. Ele usa os mesmos eventos normalizados, meses, títulos, referências, corpos e tabelas da folha completa, mas isola a narrativa administrativa do semestre para conferência rápida antes da assinatura.

`folha_alteracoes.pdf`: prévia visual para conferência.

`validacao.txt`: o que passou, o que falhou e o que precisa revisão.

`justificativa.txt`: de onde vieram os dados e como o sistema decidiu.

`variables.json`: snapshot técnico das variáveis usadas.

`pacote.zip`: entrega individual.

## 15. Pacote geral

Ao final, o sistema gera pacote de entrega:

- `PACOTE_ENTREGA_SECRETARIA.zip`;
- `PACOTE_ENTREGA_SECRETARIA_REVISADO.zip`, quando houver revisão final;
- relatórios;
- logs;
- manifesto;
- hash SHA-256;
- amostra de conferência.

Classificações:

- `FOLHAS_PRONTAS_ASSINATURA`;
- `REVISAR_MANUALMENTE`;
- `BLOQUEADAS`;
- `HOTFIX_APLICADO`;
- `RELATORIOS`;
- `LOGS`;
- `AMOSTRA_CONFERENCIA`.

O pacote deve ser navegável por humano, não apenas por sistema.

## 16. Validação

Níveis:

`OK`: passou.

`WARNING`: pode seguir com ciência ou revisão, conforme a regra da secretaria.

`ERROR`: bloqueia ou exige correção.

`CRITICAL`: não deve ser entregue.

Exemplos de OK:

- `OK_ODT_VALID`
- `OK_TEMPLATE_USED`
- `OK_ALL_MONTHS_PRESENT`
- `OK_QMS_NORMALIZED`

Exemplos de warning:

- `WARN_TEMPO_PENDENTE_VALIDACAO`
- `WARN_QMS_GENERICO`
- `WARN_EVENT_TITLE_MISSING`
- `WARN_TABLE_UNREPAIRED`
- `WARN_MONTH_WITHOUT_EVENTS`

Exemplos de error:

- `ERR_TEMPLATE_IGNORED`
- `ERR_QMS_RAW_LEAKED`
- `ERR_ODT_INVALIDO`
- `ERR_MONTH_DUPLICATED`
- `ERR_MISSING_REQUIRED_MONTH`
- `ERR_TEMPO_CALCULO_FAILED`
- `ERR_TEMPLATE_PLACEHOLDER_UNRESOLVED`

Validação não é enfeite. Ela é a diferença entre "arquivo gerado" e "documento pronto para conferência responsável".

## 17. Justificativa

A justificativa responde:

- qual foi a fonte;
- o que foi extraído;
- o que foi filtrado;
- como o tempo foi calculado ou transcrito;
- quais pendências existem;
- por que o documento foi classificado como pronto, revisar ou bloqueado.

Ela protege o operador. Quando alguém perguntar por que um evento não entrou, por que o QMS está vazio, ou por que a folha ficou em revisão, a resposta deve estar na justificativa e na validação.

## 18. Memória do Compilador

Tudo que entra e sai deve ser salvo:

- PDF SiCaPEx;
- PDF de alteração;
- ODT modelo;
- ODT final;
- PDF final;
- TXT;
- JSON;
- ZIP.

Cada arquivo deve ter:

- caminho;
- hash;
- papel;
- vínculo com execução;
- vínculo com militar, se possível.

Isso permite:

- reprocessar;
- auditar;
- provar origem;
- comparar versões;
- corrigir sem recomeçar.

## 19. Reprocessamento e hotfix

Se uma folha tem problema, o lote inteiro não deve ser refeito sem necessidade.

O sistema deve permitir:

- reprocessar um militar;
- corrigir QMS;
- aplicar modelo;
- refazer PDF;
- manter versão anterior;
- registrar hotfix.

O hotfix não deve apagar o erro original. Deve preservar antes/depois para auditoria.

## 20. Fluxo de entrega final

Fluxo real:

1. Importar SiCaPEx.
2. Importar fontes de alterações.
3. Gerar lote.
4. Classificar.
5. Revisar.
6. Promover prontas.
7. Separar revisão manual.
8. Gerar pacote revisado.
9. Conferir amostra.
10. Assinar.

## 21. Exemplo de estado final

Exemplo operacional de lote:

- 52 folhas analisadas;
- 48 prontas para assinatura;
- 4 revisar manualmente;
- 0 bloqueadas;
- ZIP revisado sem corrupção;
- duplicidades 0;
- SHA-256 calculado;
- amostra de conferência presente.

Isso significa que o lote está operacionalmente fechado, mas ainda exige conferência humana dos itens em revisão manual e validação de tempo onde houver warning.

## 22. Checklist humano

Antes da assinatura:

- abrir `CHECKLIST_ASSINATURA_REVISADO.txt`;
- conferir a amostra;
- abrir alguns PDFs;
- conferir assinatura;
- conferir QMS;
- conferir 2ª Parte;
- conferir folhas em `REVISAR_MANUALMENTE`;
- não assinar `BLOQUEADAS`;
- registrar ciência de tempo pendente se houver.

## Contrato de Formatação ODT

O contrato de formatação ODT separa aparência documental de semântica administrativa. O ODT de referência visual deve ser tratado como fixture visual: ele mostra como a Folha deve parecer, mas não fixa assinatura, não substitui cálculo de tempo e não vira verdade absoluta de filtragem de eventos.

O contrato controla:

- fonte e tamanho;
- cabeçalho e continuação;
- mês sublinhado;
- modo de mês vazio;
- título, referência de BI e corpo;
- tabela;
- comportamento;
- 2ª Parte;
- assinatura como bloco variável;
- estilos ODT em `content.xml` e `styles.xml`.

O modo compacto de mês vazio é válido quando configurado pela OM:

```text
DEZEMBRO: Sem Alteração.
```

O modo em bloco continua válido quando configurado:

```text
DEZEMBRO:
Sem alterações.
```

Eventos de beneficiário, pagamento e terceiros podem ser filtrados por política operacional futura. Isso não deve ser tratado como perda silenciosa: cada remoção deve aparecer em `variables.filtered_events[]`, com motivo, fonte e política aplicada. Tabelas com terceiros podem ser individualizadas para o militar, registrando `table_policy`.

Cabeçalhos podem estar no corpo do ODT ou em `styles.xml`/`master-page`/`header`. O validador deve reconhecer esses casos para evitar falso erro.

ODT visual e ODT executável são coisas diferentes. O primeiro pode orientar aparência. O segundo precisa dos marcadores SISGES para permitir substituição controlada. Se o operador enviar um ODT final manual sem marcadores, ele vira referência visual e não deve produzir uma folha com placeholders remanescentes.

Conteúdo potencialmente sensível na 1ª Parte, como CPF, beneficiário, pagamento, arma de fogo, dados de terceiros, conta bancária, SIGMA, PAF ou CRAF, não é removido automaticamente nesta etapa. O Compilador apenas registra `WARN_POSSIBLE_SENSITIVE_EVENT` e `WARN_REVIEW_BEFORE_SIGNATURE` para obrigar conferência antes da assinatura.

Quando houver dúvida normativa sobre filtragem, assinatura ou exposição de dados, este ponto deve ser validado pela secretaria conforme norma vigente e modelo oficial adotado pela OM.

## 23. Erros clássicos e prevenção

| Erro | Causa | Impacto | Como o SISGES detecta | Correção |
| --- | --- | --- | --- | --- |
| Modelo ODT ignorado | Renderizador caiu para template interno | Documento com aparência divergente | `ERR_TEMPLATE_IGNORED` | Reprocessar usando modelo oficial |
| QMS bruto vazando | Valor do PDF/SiCaPEx usado sem normalização | Cabeçalho com dado sujo | `ERR_QMS_RAW_LEAKED` | Normalizar QMS e reprocessar |
| Nome de guerra errado | Parser capturou referência de BI ou texto vizinho | Cabeçalho incorreto | warning de nome inválido | Corrigir cadastro/importação |
| Data de nascimento usada como praça | Regex global no PDF SiCaPEx | Cálculo de tempo errado | regra de data suspeita | Reimportar com parser ancorado |
| Mês duplicado | Agrupamento incorreto | Folha inconsistente | `ERR_MONTH_DUPLICATED` | Reagrupar eventos |
| Mês ausente | Evento sem mês ou renderização truncada | Folha incompleta | `ERR_MISSING_REQUIRED_MONTH` | Reprocessar semestre |
| Título colado ao corpo | Parser não separou referência | Conferência difícil | `WARN_EVENT_TITLE_MISSING` | Recuperar título ou revisar |
| Tabela quebrada | Extração PDF perdeu estrutura | Documento desalinhado | `WARN_TABLE_UNREPAIRED` | Reparar tabela ou revisar manualmente |
| Assinatura errada | Classificação oficial/praça falhou | Documento assinado por autoridade incorreta | `ERR_SIGNATURE_MISSING` ou validação de assinatura | Corrigir regra e reprocessar |
| PDF não gerado | Conversão LibreOffice indisponível | Falta prévia visual | `WARN_PDF_PREVIEW_NOT_GENERATED` | Gerar PDF em ambiente com conversor |
| Tempo transcrito tratado como cálculo | Fonte histórica usada como cálculo novo | Tempo sem validação | status `HISTORICO_NAO_RECALCULADO` | Rodar cálculo ou revisar |
| Arquivo temporário perdido | Output ficou fora da memória | Sem auditoria | falta de `CompilerFile`/hash | Reprocessar salvando memória |
| Dry-run confundido com commit | Execução de teste gravou ou commit não gravou | Banco incoerente | relatório de modo | Reexecutar modo correto |

## 24. Conclusão operacional

O Compilador não substitui a secretaria. Ele organiza, acelera, padroniza e expõe pendências.

A decisão final continua humana quando envolve:

- validação normativa;
- tempo de serviço sensível;
- assinatura;
- casos divergentes;
- fonte ausente.

O ganho real é:

- reduzir retrabalho;
- reduzir erro oculto;
- gerar pacote padronizado;
- deixar rastro;
- permitir entrega sob pressão com controle.

Quando houver dúvida normativa, a regra é explícita: este ponto deve ser validado pela secretaria conforme norma vigente e modelo oficial adotado pela OM.

## Nota de Fechamento do Contrato Visual ODT de Referencia

Contrato visual nao e politica semantica de conteudo. Ele define fonte, espacamento, cabecalho, meses, tabelas, comportamento, 2a Parte e assinatura como forma documental.

A decisao de incluir, excluir ou filtrar eventos pertence a politica operacional rastreada, com registro em `variables.filtered_events[]` quando aplicada. Isso evita misturar formatacao com decisao administrativa de conteudo.
