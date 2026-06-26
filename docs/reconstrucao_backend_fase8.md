# Reconstrucao tecnica do backend SISGES - Fase 8

Data: 2026-05-03

## 1. Diagnostico da fase

O SISGES ja possuia modulos importantes, mas o uso diario ainda exigia navegar entre telas isoladas para descobrir pendencias. Nao havia caixa de entrada unificada, visao consolidada do militar, regras cruzadas auditaveis nem CTAs operacionais explicaveis.

## 2. Arquitetura-alvo

- `modules/consistencia`: motor deterministico de regras cruzadas.
- `modules/ops_center`: caixa de entrada operacional materializada em banco.
- `modules/militar_360`: consolidacao do militar, historico e timeline.
- `modules/acoes_sugeridas`: tradutor de inconsistencias em proximas acoes.
- `workflow_items`: tabela operacional para Home, dashboard e rotinas de secretaria.

## 3. Arquivos criados/alterados

- Criados: `modules/ops_center`, `modules/militar_360`, `modules/consistencia`, `modules/acoes_sugeridas`.
- Criados: `apps/web/routes/ops_center.py`, `apps/web/routes/militar_360.py`, `apps/web/routes/consistencia.py`, `apps/web/routes/acoes_sugeridas.py`.
- Alterados: `infra/persistence/models.py`, `infra/persistence/seed.py`, `apps/web/app.py`, `apps/web/routes/__init__.py`.
- Alterado: `apps/web/routes/dashboard.py` para a Home consumir pendencias reais do Ops Center.
- Migration: `migrations/versions/20260503_0004_workflow_items.py`.

## 4. Codigo por arquivo

Endpoints entregues:

- `GET /ops-center/inbox`
- `GET /ops-center/inbox/summary`
- `POST /ops-center/inbox/rebuild`
- `PATCH /ops-center/inbox/{item_id}/resolve`
- `GET /militar-360/{militar_id}`
- `GET /militar-360/{militar_id}/timeline`
- `POST /consistencia/reprocessar`
- `GET /consistencia/militar/{militar_id}`
- `GET /consistencia/summary`
- `POST /acoes-sugeridas/executar`
- `GET /dashboard/pending` agora retorna inbox operacional real.
- `GET /dashboard/metrics` usa contagem real de pendencias abertas e criticas.

Regras deterministicas implementadas:

- calculo salvo sem `data_praca`;
- CTSM sem calculo aprovado;
- CTSM emitida com snapshot desatualizado;
- folha com vinculo de militar inexistente ou periodo invalido;
- documento sem hash ou sem `template_version` quando gerado pelo compilador;
- periodo de servico com sobreposicao;
- data final menor que inicial;
- movimentacao sem origem/destino;
- tarefa concluida sem artefato esperado.

## 5. Criterios de aceite

- Inbox operacional deve materializar inconsistencias em `workflow_items`.
- Rebuild deve ser idempotente por fingerprint.
- Summary deve retornar agrupamento por modulo, severidade e proxima acao.
- Militar 360 deve consolidar dados, periodos, calculos, folhas, CTSMs, documentos, tarefas e timeline.
- Consistencia deve expor regras, severidade, score, motivo e acao recomendada.
- Acoes sugeridas devem retornar alvo operacional explicavel, sem alteracao automatica perigosa.

## 6. Riscos restantes

- A Home ainda precisa consumir `/ops-center/inbox/summary` para refletir a melhoria visualmente.
- Algumas acoes sugeridas sao orientativas; automacoes reais devem ser adicionadas caso a caso.
- Regras juridicas continuam parametrizadas e conservadoras, sem inferencia livre.
- `workflow_items` nao possui ownership por secao/responsavel ainda.

## 7. Rollback

1. Remover routers da Fase 8 em `apps/web/app.py`.
2. Reverter `modules/ops_center`, `modules/militar_360`, `modules/consistencia` e `modules/acoes_sugeridas`.
3. Executar downgrade da migration `20260503_0004`, se aplicada.
4. Remover permissoes da Fase 8 no seed.
5. A tabela `workflow_items` pode ser descartada sem afetar dados de dominio.
