# Módulo Tarefas — Arquitetura Operacional SISGES

## 1. Diagnóstico do estado atual

O SISGES já possui uma base inicial para tarefas, mas o módulo ainda não está no nível operacional que a secretaria precisa.

Estado atual verificado:

- Backend:
  - `GET /tarefas`
  - `POST /tarefas`
  - `PATCH /tarefas/{tarefa_id}`
  - permissões: `mod.tarefas.view`, `mod.tarefas.create`, `mod.tarefas.edit`, `mod.tarefas.assign`, `mod.tarefas.close`
  - modelo `TarefaModel` com vínculo a militar, missão, responsável, revisor, prazo, status, bloqueio e resultado.

- Frontend:
  - rota `/tarefas` está prevista na navegação;
  - `endpoints.tarefas` e `endpoints.tarefaById(id)` existem;
  - a página `app/tarefas/page.tsx` não existe neste checkout;
  - a navegação ainda marca Tarefas como `route-pending`.

- Integrações existentes:
  - `Militar 360` já consolida tarefas vinculadas ao militar;
  - `Consistência` já detecta tarefa concluída sem artefato;
  - `Ops Center` materializa pendências sistêmicas em `workflow_items`;
  - `Ações Sugeridas` já aponta para `/tarefas/{referencia_id}` quando a pendência exige registrar artefato.

Conclusão:
o módulo existe como CRUD técnico, mas ainda não funciona como centro operacional de controle da secretaria.

## 2. Problema operacional que o módulo deve resolver

A secretaria militar trabalha com demandas pequenas e críticas o tempo todo:

- corrigir cadastro de militar;
- completar data de praça;
- revisar tempo de serviço;
- emitir CTSM;
- compilar Folha de Alterações;
- revisar documento;
- anexar artefato;
- responder pendência de missão;
- conferir assinatura;
- acompanhar tarefas por seção;
- separar o que é do operador, do revisor, da secretaria e do comando.

Sem um módulo de tarefas integrado, o sistema vira vários módulos isolados. O operador precisa lembrar manualmente que uma inconsistência no cálculo gera impacto em CTSM, que uma folha bloqueada precisa de revisão, que um documento sem hash precisa reprocessamento e que uma tarefa concluída sem artefato não deveria desaparecer.

O módulo Tarefas deve ser o controle de trabalho humano do SISGES.

## 3. Conceito central

Tarefa é uma unidade de trabalho humano rastreável.

Ela pode nascer de três formas:

1. Manual:
   criada por operador, chefe de seção ou dev.

2. Assistida:
   criada a partir de uma pendência detectada pelo sistema, mas assumida por uma pessoa.

3. Automática controlada:
   criada por regra determinística do SISGES, sem executar decisão sensível sozinha.

Tarefa não substitui `workflow_items`.

Diferença:

- `workflow_items` são alertas materializados pelo sistema.
- `tarefas` são compromissos atribuídos a pessoas ou seções.

Uma pendência do Ops Center pode virar tarefa, mas nem toda tarefa precisa nascer de uma pendência.

## 4. Modelo operacional proposto

### 4.1 Campos principais

O modelo atual já contém a base mínima:

- `titulo`
- `descricao`
- `tipo`
- `prioridade`
- `status`
- `origem_modulo`
- `militar_id`
- `missao_id`
- `responsavel_user_id`
- `revisor_user_id`
- `criado_por_user_id`
- `prazo`
- `data_inicio`
- `data_conclusao`
- `bloqueada`
- `motivo_bloqueio`
- `resultado_resumido`
- `observacoes`

Campos recomendados para evolução:

- `secao_responsavel`
- `divisao_responsavel`
- `referencia_tipo`
- `referencia_id`
- `workflow_item_id`
- `document_id`
- `artefato_tipo`
- `artefato_path`
- `artefato_sha256`
- `checklist_json`
- `historico_json`
- `created_from_rule`
- `blocked_by_task_id`
- `completed_by_user_id`
- `closed_by_user_id`
- `closed_at`

Esses campos devem ser adicionados por migration em fase própria, sem quebrar compatibilidade com o CRUD atual.

### 4.2 Status

Status operacionais recomendados:

- `nova`
- `triagem`
- `em_andamento`
- `aguardando_terceiro`
- `aguardando_revisao`
- `bloqueada`
- `concluida`
- `cancelada`

Status técnico anterior ainda deve ser aceito para compatibilidade, mas a UI deve conduzir o operador para os status acima.

### 4.3 Prioridade

Prioridades:

- `critica`
- `alta`
- `media`
- `baixa`

Regra:
prioridade deve afetar ordenação, painel de secretaria e alertas, mas não deve executar ação automaticamente.

### 4.4 Tipo

Tipos recomendados:

- `cadastro`
- `tempo_servico`
- `folha_alteracao`
- `ctsm`
- `documento`
- `compilador`
- `missao`
- `assinatura`
- `auditoria`
- `suporte`
- `outro`

## 5. Arquitetura de camadas

### 5.1 Backend

Estrutura recomendada:

```text
modules/tarefas/
  application/
    schemas.py
    services.py
    task_factory.py
    task_rules.py
  infrastructure/
    repository.py
  domain/
    statuses.py
    priorities.py
```

Responsabilidades:

- `schemas.py`:
  contratos de entrada e saída.

- `repository.py`:
  leitura e escrita no banco.

- `services.py`:
  regras de criação, transição de status, conclusão, bloqueio, reabertura e validação.

- `task_factory.py`:
  criação padronizada a partir de módulos como Compilador, Folhas, CTSM, Gestão de Pessoal, Ops Center e Consistência.

- `task_rules.py`:
  regras determinísticas para sugerir ou criar tarefas.

- `domain/statuses.py`:
  enum/constantes de status válidos.

### 5.2 API

Endpoints atuais devem permanecer:

- `GET /tarefas`
- `POST /tarefas`
- `PATCH /tarefas/{tarefa_id}`

Endpoints recomendados:

- `GET /tarefas/resumo`
- `GET /tarefas/minhas`
- `GET /tarefas/secao`
- `GET /tarefas/{tarefa_id}`
- `POST /tarefas/from-workflow-item/{item_id}`
- `POST /tarefas/{tarefa_id}/iniciar`
- `POST /tarefas/{tarefa_id}/bloquear`
- `POST /tarefas/{tarefa_id}/concluir`
- `POST /tarefas/{tarefa_id}/reabrir`
- `POST /tarefas/{tarefa_id}/anexar-artefato`
- `GET /tarefas/{tarefa_id}/historico`

Regra:
os endpoints de transição devem validar status e permissão. A UI não deve manipular status sensível apenas por PATCH livre.

### 5.3 Frontend

Tela principal:

```text
/tarefas
```

Layout recomendado:

- visão "Minhas tarefas";
- visão "Minha seção";
- visão "Toda secretaria" para usuários autorizados;
- quadro por status;
- lista densa;
- filtros por:
  - status;
  - prioridade;
  - tipo;
  - responsável;
  - seção;
  - militar;
  - origem;
  - prazo;
  - bloqueadas;
- painel lateral de detalhe;
- ações rápidas:
  - iniciar;
  - atribuir;
  - bloquear;
  - concluir;
  - reabrir;
  - anexar resultado;
  - abrir referência.

Não usar layout de landing page. O módulo é ferramenta de trabalho diário.

## 6. Integração com módulos SISGES

### 6.1 Gestão de Pessoal

Uso:

- criar tarefa para corrigir cadastro;
- completar data de praça;
- revisar QMS;
- revisar divisão/seção;
- conferir militar inativo;
- vincular tarefa ao militar.

Exemplo:

```text
Tarefa: Completar data de praça
Tipo: cadastro
Origem: gestao_pessoal
Militar: militar_id
Prioridade: alta
```

### 6.2 Cálculo de Tempo

Uso:

- revisar cálculo pendente;
- validar tempo de serviço;
- corrigir período inconsistente;
- aprovar snapshot para CTSM.

Regra:
cálculo sensível deve gerar tarefa de revisão quando houver warning relevante.

### 6.3 CTSM

Uso:

- emitir CTSM a partir de cálculo aprovado;
- revisar CTSM sem cálculo;
- reemitir CTSM desatualizada;
- anexar documento emitido.

Regra:
CTSM emitida deve poder encerrar tarefa automaticamente somente se houver `document_id` e artefato registrado.

### 6.4 Folhas de Alterações

Uso:

- compilar folha;
- revisar folha com pendência;
- validar assinatura;
- corrigir folha bloqueada;
- anexar pacote final.

Regra:
folha classificada como `REVISAR_MANUALMENTE` deve poder gerar tarefa para responsável da seção.

### 6.5 Compilador

Uso:

- gerar tarefa quando run falha;
- revisar warning crítico;
- reprocessar documento;
- validar pacote completo;
- resolver placeholder, template ou QMS bruto.

Regra:
run com `FALHOU` deve sugerir tarefa, mas não deve criar repetidas tarefas duplicadas.

### 6.6 Documentos

Uso:

- revisar documento sem hash;
- anexar versão final;
- baixar/conferir documento;
- rastrear documento gerado por tarefa.

### 6.7 Ops Center

Uso:

- transformar `workflow_item` em tarefa assumida;
- separar alerta automático de trabalho humano;
- resolver workflow item quando a tarefa vinculada for concluída com evidência.

Regra:
`workflow_item` não deve desaparecer só porque uma tarefa foi criada. Ele deve ficar vinculado até haver resolução.

### 6.8 Militar 360

Uso:

- mostrar todas as tarefas vinculadas ao militar;
- exibir tarefas na timeline;
- permitir abrir tarefa diretamente do histórico do militar.

### 6.9 Quadro

Uso:

- apoio visual em reuniões de secretaria;
- tarefas podem referenciar quadro operacional por `referencia_tipo=quadro`.

## 7. Fluxo operacional recomendado

```text
Módulo detecta necessidade
        ↓
Cria alerta ou sugestão
        ↓
Operador converte em tarefa ou cria manualmente
        ↓
Tarefa é atribuída a pessoa/seção
        ↓
Execução registra progresso, bloqueio e observações
        ↓
Conclusão exige resultado ou artefato quando aplicável
        ↓
SISGES atualiza timeline, Ops Center e dashboards
```

## 8. Regras de criação automática

Criar tarefa automaticamente apenas quando a regra for determinística e não causar dano operacional.

Pode criar:

- run do Compilador falhou;
- documento esperado não foi gerado;
- CTSM sem cálculo aprovado;
- Folha bloqueada;
- tarefa documental concluída sem artefato;
- período de serviço inconsistente;
- militar sem dado obrigatório para fluxo em andamento.

Não criar automaticamente:

- decisão normativa;
- julgamento jurídico;
- escolha de assinatura;
- alteração de cadastro sensível;
- exclusão;
- emissão final sem validação.

Nesses casos, criar sugestão ou pendência para revisão humana.

## 9. Antiduplicidade

Toda tarefa criada por regra deve ter fingerprint.

Formato sugerido:

```text
{origem_modulo}:{tipo}:{referencia_tipo}:{referencia_id}:{militar_id}
```

Exemplo:

```text
compilador:run_falhou:compiler_run:abc123:16
```

Se já existir tarefa aberta com o mesmo fingerprint, atualizar a existente em vez de criar duplicata.

## 10. Permissões

Permissões atuais:

- `mod.tarefas.view`
- `mod.tarefas.create`
- `mod.tarefas.edit`
- `mod.tarefas.assign`
- `mod.tarefas.close`

Uso recomendado:

- `view`: ver tarefas no escopo autorizado.
- `create`: criar tarefa manual.
- `edit`: editar título, descrição, prazo, prioridade, observações.
- `assign`: alterar responsável, seção ou revisor.
- `close`: concluir, cancelar ou reabrir tarefa.

Escopo:

- usuário comum: próprias tarefas e tarefas da seção.
- operador: tarefas da seção e tarefas vinculadas aos módulos que opera.
- admin/dev: visão completa.

## 11. Dashboard e indicadores

Resumo operacional:

- total abertas;
- vencidas;
- vencem hoje;
- bloqueadas;
- aguardando revisão;
- críticas;
- por seção;
- por responsável;
- por origem;
- por tipo.

Indicadores úteis:

- tempo médio até conclusão;
- tarefas concluídas sem artefato;
- tarefas reabertas;
- tarefas sem responsável;
- tarefas geradas automaticamente;
- módulos com mais pendências.

## 12. Contrato de conclusão

Uma tarefa pode ser concluída livremente quando for administrativa simples.

Mas, se a tarefa for documental ou sistêmica, conclusão deve exigir evidência:

- `resultado_resumido`;
- `document_id`;
- `artefato_path`;
- `artefato_sha256`;
- ou justificativa explícita.

Exemplos que exigem evidência:

- emitir CTSM;
- compilar Folha;
- gerar declaração;
- reprocessar documento;
- validar pacote;
- corrigir folha bloqueada.

## 13. Histórico e auditoria

Toda alteração relevante deve gerar evento:

- criação;
- mudança de responsável;
- mudança de prioridade;
- mudança de status;
- bloqueio;
- desbloqueio;
- conclusão;
- reabertura;
- anexo de artefato.

Modelo recomendado:

```text
tarefa_evento
- id
- tarefa_id
- actor_user_id
- event_type
- before_json
- after_json
- note
- created_at
```

Isso evita que a tarefa vire apenas uma linha mutável sem rastreabilidade.

## 14. Roadmap de implementação

### Fase 1 — Fechar a tela operacional

- Criar `app/tarefas/page.tsx`.
- Consumir endpoints reais existentes.
- Listar tarefas.
- Criar tarefa.
- Editar status/prioridade/responsável.
- Filtrar por status, prioridade e responsável.
- Remover `route-pending` da navegação.
- Build frontend.

### Fase 2 — Serviço de domínio

- Criar `TarefasService`.
- Validar transições.
- Setar `criado_por_user_id` pelo usuário logado.
- Criar código automático.
- Padronizar status/prioridades.

### Fase 3 — Integração com Ops Center

- Criar tarefa a partir de `workflow_item`.
- Vincular tarefa a item operacional.
- Resolver item quando tarefa for concluída com evidência.

### Fase 4 — Evidência e artefatos

- Anexar documento/arquivo/resultado.
- Validar conclusão documental.
- Exibir evidências na UI.

### Fase 5 — Integração ampla

- Criar atalhos em:
  - Gestão de Pessoal;
  - Militar 360;
  - Folhas;
  - CTSM;
  - Compilador;
  - Documentos;
  - Ops Center.

### Fase 6 — Auditoria

- Criar `tarefa_evento`.
- Exibir histórico.
- Gerar relatório de tarefas da secretaria.

## 15. Critério de aceite operacional

O módulo Tarefas estará pronto quando:

- existir tela funcional em `/tarefas`;
- não houver mock enganoso;
- tarefas puderem ser criadas e editadas;
- tarefas puderem ser atribuídas;
- filtros forem úteis para a secretaria;
- tarefas aparecerem no Militar 360;
- pendências do Ops Center puderem virar tarefa;
- tarefas documentais exigirem resultado;
- dashboard mostrar pendências reais;
- permissões forem respeitadas;
- build frontend passar;
- testes backend cobrirem criação, listagem, edição, filtros e transições.

## 16. Próxima execução recomendada

Implementar primeiro a Fase 1.

Motivo:
o backend já possui contrato mínimo e a ausência mais visível é a tela `/tarefas`. A secretaria precisa enxergar e operar as tarefas antes de evoluir regras automáticas mais profundas.

Depois disso, implementar `TarefasService` para deixar de usar apenas PATCH livre.

## 17. Estado implementado nesta rodada

As fases centrais do documento foram operacionalizadas sem mock:

- Fase 1:
  - `/tarefas` foi criada no frontend;
  - a navegação deixou de marcar o módulo como `route-pending`;
  - a tela consome endpoints reais;
  - há visão por seção, minhas tarefas e toda secretaria;
  - há filtros por status, prioridade, busca textual e inclusão de encerradas;
  - há criação manual de tarefa.

- Fase 2:
  - `TarefasService` foi criado;
  - status e prioridades passaram a ter constantes de domínio;
  - criação define `criado_por_user_id`;
  - o código operacional `TRF-000001` é gerado automaticamente;
  - ações sensíveis passaram por endpoints específicos, não apenas PATCH livre.

- Fase 3:
  - tarefa pode ser criada a partir de `workflow_item`;
  - a criação é idempotente por `fingerprint`;
  - a tarefa mantém vínculo com o item operacional;
  - ao concluir com evidência, o item do Ops Center é resolvido.

- Fase 4:
  - artefato, hash, documento e resultado podem ser registrados;
  - tarefas documentais/sistêmicas exigem evidência antes de conclusão;
  - a UI mostra e permite registrar resultado/artefato.

- Fase 6:
  - `tarefa_evento` registra criação, edição, início, bloqueio, conclusão, reabertura e anexação de artefato;
  - a UI exibe histórico auditável da tarefa.

Validação executada:

```bash
python -m pytest tests/test_tarefas_operacional.py tests/test_qms_normalization.py tests/test_template_odt_rendering.py tests/test_folha_header_rendering.py tests/test_compiler_memory_service.py tests/test_reference_folha_pdf_parser.py tests/test_ysak_format_contract.py tests/test_folha_empty_month_modes.py tests/test_event_filter_policy.py
python -m ruff check .
npm run build
```

Resultado:

- 40 testes backend passaram;
- `ruff` passou;
- `npm run build` passou;
- rota `/tarefas` entrou no build Next;
- verificação no navegador confirmou que `/tarefas` não é 404 e redireciona para login quando não há sessão.

Pendência posterior:

- integrar atalhos contextuais nos módulos Gestão de Pessoal, Militar 360, Folhas, CTSM, Compilador, Documentos e Ops Center;
- gerar relatório operacional consolidado de tarefas da secretaria;
- validar fluxo autenticado em navegador real com usuário operador/dev.
