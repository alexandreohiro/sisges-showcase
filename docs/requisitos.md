# Requisitos funcionais do SisGeS

Extraído do código existente (rotas, módulos e regras já implementadas), não de um documento de especificação anterior — este documento descreve o que o sistema **faz hoje**.

## Domínio

Sistema de apoio a rotinas de secretaria com foco em gestão de pessoal militar: cadastro, cálculo de tempo de serviço, compilação de documentos oficiais (Folhas de Alterações) a partir de fontes como SiCaPEx, e gestão operacional (tarefas, notificações, quadro).

## Módulos e responsabilidades

| Módulo | Responsabilidade |
|---|---|
| `auth` | Login/logout, sessão por cookie assinado, "me". |
| `users` | CRUD de usuários do sistema. |
| `permissions` / `roles` | Papéis (`dev`, `admin`, `operador`, `consulta`) e permissões granulares por rota. |
| `acessos` | Vault de auditoria de credenciais (snapshot cifrado de alterações de usuário). |
| `gestao_pessoal` | Núcleo de cadastro de militares: identificação, filiação, contato, situação militar, dados funcionais. Importação via texto/PDF (SiCaPEx). |
| `calculo_tempo_servico` | Consolidação de períodos de serviço, classificação de buckets de tempo, preview/diff/aprovação, snapshot histórico com justificativa e base legal. |
| `compilador` | Pipeline de extração de PDF (SiCaPEx, Folhas) → resolução de pendências → renderização ODT/PDF a partir de template oficial. |
| `folhas` | Geração de Folhas de Alterações ligadas a militar/período; cria tarefa e notificação automaticamente ao gerar. |
| `declaracoes` | Geração de declarações administrativas a partir de modelo. |
| `documents` | Registro/metadados de documentos gerados pelo sistema (hash, versão de template, rastreabilidade); inventário e auditoria do dataset da secretaria. |
| `validacao` | Validação estrutural, semântica e textual de saídas do compilador (placeholder não resolvido, tabela não reconstruída, etc. — ver `docs/ERROS_E_HOTFIX_FOLHAS.md`). |
| `tarefas` | Tarefas operacionais com prioridade/status, vinculadas a militar/origem. |
| `quadro` | Quadro/board de visualização operacional. |
| `ctsm` | Cálculo/registro relacionado a tempo de serviço militar (CTSM). |
| `ops_center` | Caixa de entrada operacional: materializa inconsistências detectadas em `workflow_items`, com resumo por módulo/severidade. |
| `militar_360` | Visão consolidada de um militar: dados, períodos, cálculos, folhas, CTSMs, documentos, tarefas e timeline. |
| `consistencia` | Motor determinístico de regras cruzadas (ex.: cálculo sem `data_praca`, período com sobreposição, tarefa concluída sem artefato). |
| `acoes_sugeridas` | Traduz inconsistências detectadas em próximas ações operacionais explicáveis (sem automação perigosa). |
| `feature_flags` | Flags de funcionalidade controladas via seed/banco. |

## Requisitos não funcionais (já implementados)

- **Autenticação e autorização**: sessão por cookie, RBAC por permissão granular, modo "dev" para ações administrativas restritas.
- **Auditoria**: snapshot cifrado de alterações de credencial de usuário; hash/versão de template em documentos gerados; rastreabilidade de execução do compilador (`compiler_run`, `compiler_file`, `compiler_validation`).
- **Atomicidade**: fluxos compostos (folha+tarefa+notificação, cálculo+snapshot) são transacionais via `atomic(db)`.
- **Healthcheck operacional**: `/health`, `/health/live`, `/health/ready` distinguem processo vivo de banco indisponível.
- **Higiene de dados pessoais**: dados de `data/` (PDFs, ODTs, banco local) nunca devem ser versionados — ver `SECURITY.md` e `docs/SANEAMENTO_HISTORICO_GIT_FASE1.md` para o incidente que motivou essa regra ser reforçada.

## Requisitos não funcionais (em roadmap, ver `roadmap.md`)

- CI/CD automatizado (GitHub Actions).
- MySQL como banco de homologação/produção (backlog já detalhado em `docs/PLANO_EVOLUCAO_MYSQL_CLEAN_ARCH.md`).
- Containerização (Docker/Compose) para paridade dev/homolog.
- Observabilidade mínima (logs estruturados já existem; agregação/alerta ainda não).
