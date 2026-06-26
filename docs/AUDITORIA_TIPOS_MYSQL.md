# Auditoria de Tipos para MySQL

Documento de levantamento (read-only). Nenhum tipo/tamanho de coluna foi alterado
neste documento ou no codigo como parte desta auditoria. Mudancas de tipo exigem
migration Alembic e decisao explicita sobre compatibilidade com dados existentes
em SQLite local — fora do escopo deste levantamento.

Fonte unica de modelos SQLAlchemy do projeto: `infra/persistence/models.py`.
Confirmado por busca em `modules/*/` que nao existe nenhum outro arquivo com
`mapped_column`/`Column(...)`/`__tablename__` — os modulos so tem schemas
Pydantic (DTOs de API), nao tabelas. Por isso a secao 1 cobre apenas
`infra/persistence/models.py`.

Motivacao: SQLite nao aplica limite de tamanho em `String` sem `length=`
(coluna fica `VARCHAR` sem limite pratico / `TEXT`-like). MySQL exige um
tamanho explicito para `VARCHAR` indexavel e tem limite de 65.535 bytes por
linha somando todas as colunas — colunas `String` sem tamanho quebram ou
forcam o driver a escolher um tamanho default inadequado quando a migration
for rodada contra MySQL.

## 1. Colunas `String`/`sa.String` sem `length=` explicito

Tabela com `arquivo:linha`, classe/tabela, campo e tamanho recomendado.
Recomendacoes seguem o padrao ja usado no restante do arquivo para campos
semanticamente equivalentes (ex.: outros FKs de `users.id` no mesmo arquivo
ja usam `String(64)`/sem tamanho; aqui padronizamos por significado).

### 1.1 Identificadores primarios e FKs (UUID via `str(uuid4())`)

Confirmado em `modules/documents/application/services.py:31`,
`modules/users/application/services.py:92`,
`modules/compilador/application/compiler_memory_service.py` (varias linhas),
`modules/gestao_pessoal/importadores/sicapex/service.py` (varias linhas) que
todo `id` de entidade com PK string usa `str(uuid4())` — sempre 36
caracteres no formato `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`. Recomendacao:
`String(36)` para todos os pares PK/FK abaixo (precisam ter o **mesmo**
tamanho dos dois lados da FK em MySQL/InnoDB, senao o engine recusa o
indice/constraint).

| Arquivo:Linha | Classe (tabela) | Campo | Tamanho recomendado |
|---|---|---|---|
| infra/persistence/models.py:45 | UserModel (users) | id | String(36) |
| infra/persistence/models.py:75 | CredentialAuditModel (credential_audit) | user_id (FK users.id) | String(36) |
| infra/persistence/models.py:77 | CredentialAuditModel (credential_audit) | actor_user_id (FK users.id) | String(36) |
| infra/persistence/models.py:87 | RoleModel (roles) | id | String(36) |
| infra/persistence/models.py:104 | PermissionModel (permissions) | id | String(36) |
| infra/persistence/models.py:156 | WorkflowItemModel (workflow_items) | resolved_by_user_id | String(36) |
| infra/persistence/models.py:164 | DocumentModel (documents) | id | String(36) |
| infra/persistence/models.py:176-180 | DocumentModel (documents) | owner_user_id (FK users.id) | String(36) |
| infra/persistence/models.py:193 | CompilerRunModel (compiler_run) | id | String(36) |
| infra/persistence/models.py:208 | CompilerRunModel (compiler_run) | created_by_user_id (FK users.id) | String(36) |
| infra/persistence/models.py:229 | CompilerFileModel (compiler_file) | id | String(36) |
| infra/persistence/models.py:230 | CompilerFileModel (compiler_file) | run_id (FK compiler_run.id) | String(36) |
| infra/persistence/models.py:231 | CompilerFileModel (compiler_file) | document_id (FK documents.id) | String(36) |
| infra/persistence/models.py:259 | CompilerVariableSnapshotModel (compiler_variable_snapshot) | id | String(36) |
| infra/persistence/models.py:260 | CompilerVariableSnapshotModel | run_id (FK compiler_run.id) | String(36) |
| infra/persistence/models.py:261 | CompilerVariableSnapshotModel | file_id (FK compiler_file.id) | String(36) |
| infra/persistence/models.py:282 | CompilerValidationModel (compiler_validation) | id | String(36) |
| infra/persistence/models.py:283 | CompilerValidationModel | run_id (FK compiler_run.id) | String(36) |
| infra/persistence/models.py:284 | CompilerValidationModel | file_id (FK compiler_file.id) | String(36) |
| infra/persistence/models.py:405-410 | MissaoModel (missao) | responsavel_user_id (FK users.id) | String(36) |
| infra/persistence/models.py:463-468 | TarefaModel (tarefa) | document_id (FK documents.id) | String(36) |
| infra/persistence/models.py:469-474 | TarefaModel | responsavel_user_id (FK users.id) | String(36) |
| infra/persistence/models.py:475-480 | TarefaModel | revisor_user_id (FK users.id) | String(36) |
| infra/persistence/models.py:481-486 | TarefaModel | criado_por_user_id (FK users.id) | String(36) |
| infra/persistence/models.py:487-492 | TarefaModel | completed_by_user_id (FK users.id) | String(36) |
| infra/persistence/models.py:493-498 | TarefaModel | closed_by_user_id (FK users.id) | String(36) |
| infra/persistence/models.py:566 | QuadroBoardModel (quadro_board) | owner_user_id (FK users.id, NOT NULL) | String(36) |
| infra/persistence/models.py:596-601 | FolhaAlteracaoModel (folha_alteracao) | responsavel_user_id (FK users.id) | String(36) |
| infra/persistence/models.py:602-607 | FolhaAlteracaoModel | revisor_user_id (FK users.id) | String(36) |
| infra/persistence/models.py:637-642 | FolhaEventoModel (folha_evento) | user_id (FK users.id) | String(36) |
| infra/persistence/models.py:653-657 | NotificacaoModel (notificacao) | user_id (FK users.id, NOT NULL) | String(36) |
| infra/persistence/models.py:737-742 | CalculoTempoServicoModel (calculo_tempo_servico) | calculado_por_user_id (FK users.id) | String(36) |
| infra/persistence/models.py:769-774 | CTSMModel (ctsm) | document_id (FK documents.id) | String(36) |
| infra/persistence/models.py:782-787 | CTSMModel | responsavel_user_id (FK users.id) | String(36) |
| infra/persistence/models.py:788-793 | CTSMModel | revisor_user_id (FK users.id) | String(36) |
| infra/persistence/models.py:798-803 | CTSMModel | emitido_por_user_id (FK users.id) | String(36) |
| infra/persistence/models.py:852-857 | MilitarPeriodoServicoModel (militar_periodo_servico) | source_file_id (FK sicapex_import_file.id) | String(36) |
| infra/persistence/models.py:877 | SicapexImportBatchModel (sicapex_import_batch) | id | String(36) |
| infra/persistence/models.py:897 | SicapexImportFileModel (sicapex_import_file) | id | String(36) |
| infra/persistence/models.py:898-903 | SicapexImportFileModel | batch_id (FK sicapex_import_batch.id) | String(36) |
| infra/persistence/models.py:932-937 | SicapexEventoFuncionalModel (sicapex_evento_funcional) | source_file_id (FK sicapex_import_file.id) | String(36) |

### 1.2 Campos de negocio/conteudo sem FK

| Arquivo:Linha | Classe (tabela) | Campo | Tamanho recomendado | Justificativa |
|---|---|---|---|---|
| infra/persistence/models.py:46 | UserModel (users) | username | String(80) | login curto, ja com `unique=True, index=True` |
| infra/persistence/models.py:47 | UserModel (users) | display_name | String(160) | nome de exibicao |
| infra/persistence/models.py:48 | UserModel (users) | email | String(255) | limite pratico de RFC 5321/maioria dos sistemas |
| infra/persistence/models.py:49 | UserModel (users) | password_hash | String(255) | hash bcrypt/argon2 tem ~60-97 chars; 255 da folga para trocar algoritmo |
| infra/persistence/models.py:88 | RoleModel (roles) | name | String(80) | nome de role/enum-like |
| infra/persistence/models.py:105 | PermissionModel (permissions) | key | String(120) | chave de permissao (ex.: "modulo.acao") |
| infra/persistence/models.py:116 | FeatureFlagModel (feature_flags) | key (PK) | String(120) | chave de feature flag |
| infra/persistence/models.py:165 | DocumentModel (documents) | kind | String(50) | enum-like de tipo de documento |
| infra/persistence/models.py:166 | DocumentModel (documents) | filename | String(255) | limite tradicional de nome de arquivo (NTFS/ext4) |
| infra/persistence/models.py:167 | DocumentModel (documents) | status | String(50) | enum-like |
| infra/persistence/models.py:168 | DocumentModel (documents) | source_module | String(80) | nome de modulo de origem |
| infra/persistence/models.py:169 | DocumentModel (documents) | output_path | String(500) | caminho de arquivo, pode ser path completo |

## 2. Colunas `JSON` que o plano flagra como "deveria ser coluna pesquisavel"

Criterio (secao 12.6 do plano): identidade, militar_id, status, ano,
semestre, tipo_documento, role de arquivo, hashes, prazos, secoes,
responsaveis — se aparece dentro de um blob JSON e e usado como filtro de
tela/relatorio/auditoria, deveria ser coluna indexada, nao campo dentro de
JSON.

Nota: a maioria dos `*_json` do arquivo armazena *snapshots*/*payloads* de
auditoria legitimos (lista completa abaixo, com avaliacao individual).
Sinalizados como suspeitos (3) os que parecem reembutir dado ja pesquisavel
em outro lugar do mesmo registro ou que sao tipicamente filtrados.

| Arquivo:Linha | Classe (tabela) | Campo | Avaliacao |
|---|---|---|---|
| infra/persistence/models.py:148 | WorkflowItemModel (workflow_items) | payload_json | Payload de diagnostico variavel por `tipo`/`modulo` (ja tem colunas dedicadas `status`, `severidade`, `militar_id`, `referencia_tipo`/`referencia_id`). OK manter como JSON — e complemento, nao filtro primario. |
| infra/persistence/models.py:175 | DocumentModel (documents) | metadata_json | Metadados flexiveis de geracao (`kind`/`status`/`trace_id`/hashes ja sao colunas dedicadas). OK manter. |
| infra/persistence/models.py:264 | CompilerVariableSnapshotModel (compiler_variable_snapshot) | variables_json | Snapshot de variaveis de compilacao — natureza de snapshot, esperado em JSON. OK. |
| infra/persistence/models.py:265 | CompilerVariableSnapshotModel | warnings_json | Lista de avisos do snapshot — OK como JSON. |
| infra/persistence/models.py:266 | CompilerVariableSnapshotModel | pending_json | Lista de pendencias do snapshot — OK como JSON. |
| infra/persistence/models.py:267 | CompilerVariableSnapshotModel | confidence_json | Mapa de confianca por variavel — OK como JSON. |
| infra/persistence/models.py:289 | CompilerValidationModel (compiler_validation) | payload_json | Detalhe extra de uma validacao que ja tem `level`/`code`/`field` como colunas. OK. |
| infra/persistence/models.py:386 | MilitarModel (militar) | ficha_cadastro_json | **Suspeito.** Guarda o snapshot bruto da ficha de cadastro importada (provavelmente inclui `identidade`, `cpf`, nomes, datas que JA existem como colunas proprias em `MilitarModel`, linhas 300-393). Risco: dado duplicado/redundante entre JSON e colunas; se telas/relatorios um dia consultarem o JSON em vez das colunas dedicadas, perde indice. Recomenda-se manter como auditoria/snapshot de origem (rastreabilidade do import), mas garantir que nenhuma leitura de tela use este campo em vez das colunas equivalentes. |
| infra/persistence/models.py:515 | TarefaModel (tarefa) | checklist_json | Checklist de subtarefas — estrutura de lista variavel, sem padrao fixo de filtro. OK como JSON. |
| infra/persistence/models.py:546 | TarefaEventoModel (tarefa_evento) | before_json | Snapshot de auditoria "antes" do evento — payload de auditoria, esperado em JSON. OK. |
| infra/persistence/models.py:547 | TarefaEventoModel | after_json | Snapshot de auditoria "depois" do evento — OK. |
| infra/persistence/models.py:567 | QuadroBoardModel (quadro_board) | content_json | Conteudo do quadro (estrutura de board/cards), nao e dado tabular pesquisavel por natureza. OK. |
| infra/persistence/models.py:608 | FolhaAlteracaoModel (folha_alteracao) | header_json | **Suspeito.** Cabecalho da folha de alteracoes tipicamente contem `militar_id`/identidade/posto-graduacao/periodo, que ja existem como colunas em `FolhaAlteracaoModel` (`militar_id`, `periodo_inicio`, `periodo_fim`) ou em `MilitarModel`. Avaliar se algum campo do header e consultado fora do contexto de exibicao do documento (ex.: relatorio por periodo) — se sim, deveria ser coluna. |
| infra/persistence/models.py:609 | FolhaAlteracaoModel | part1_json | Conteudo estruturado da parte 1 da folha (corpo do documento) — natureza de conteudo de documento, nao filtro de tela. OK como JSON, mas se `secoes`/`responsaveis` dentro dele forem usados como filtro de listagem, ver item 12.6 do plano (secoes/responsaveis estao na lista de "nao deveria ser JSON"). Vale revisão futura do conteudo interno deste JSON. |
| infra/persistence/models.py:610 | FolhaAlteracaoModel | part2_json | Mesma observacao de part1_json — conteudo de documento, possivel presenca de "secoes"/"responsaveis" internos a revisar. |
| infra/persistence/models.py:611 | FolhaAlteracaoModel | diagnostico_json | Diagnostico de geracao/validacao do documento — payload de auditoria. OK. |
| infra/persistence/models.py:643 | FolhaEventoModel (folha_evento) | payload_json | Payload do evento de auditoria da folha — OK. |
| infra/persistence/models.py:735 | CalculoTempoServicoModel (calculo_tempo_servico) | base_legal_json | Lista/mapa de fundamentos legais citados no calculo — natureza de anexo, nao filtro tabular tipico. OK, mas se `legislacao_id`/codigo de lei aqui dentro precisar ser filtrado por relatorio, comparar com `LegislacaoModel` (tabela dedicada) e considerar FK em vez de JSON. |
| infra/persistence/models.py:794 | CTSMModel (ctsm) | conteudo_json | Conteudo estruturado do documento CTSM (corpo do certificado) — natureza de documento. OK. |
| infra/persistence/models.py:858 | MilitarPeriodoServicoModel (militar_periodo_servico) | payload_json | Payload bruto do evento de periodo de servico importado via SiCaPEx — campos relevantes (`tipo_registro`, `categoria_tempo`, `data_inicio`/`data_fim`, `status_calculo`) ja sao colunas dedicadas na mesma tabela (linhas 831-861). OK como JSON de rastreabilidade da fonte. |
| infra/persistence/models.py:885 | SicapexImportBatchModel (sicapex_import_batch) | report_json | Relatorio agregado do lote de importacao (contadores ja tem colunas dedicadas: `total_files`, `success_count`, etc.). OK como JSON de detalhe. |
| infra/persistence/models.py:915 | SicapexImportFileModel (sicapex_import_file) | warnings_json | Lista de avisos do parse do arquivo — OK como JSON. |
| infra/persistence/models.py:916 | SicapexImportFileModel | parsed_json | **Suspeito.** Conteudo parseado bruto do arquivo SiCaPEx. A tabela ja tem `status`, `militar_id`, `identidade_militar_hash`, `sha256` como colunas — mas se o conteudo parseado guarda `tipo_documento` ou `ano`/`semestre` usados em filtro de listagem do pipeline de import, valeria promover esses campos especificos para coluna. Avaliar amostra real de `parsed_json` antes de decidir. |
| infra/persistence/models.py:943 | SicapexEventoFuncionalModel (sicapex_evento_funcional) | payload_json | Payload bruto do evento funcional; campos centrais (`tipo_evento`, `subtipo_evento`, `data_inicio`, `data_fim`, `documento`) ja sao colunas dedicadas (linhas 938-942). OK como JSON de rastreabilidade. |

### 2.1 Resumo dos suspeitos para decisao futura

3 campos `JSON` marcados como suspeitos por aparente redundancia com colunas
ja pesquisaveis ou por possivelmente conter dado que e filtrado em tela:

1. `MilitarModel.ficha_cadastro_json` (infra/persistence/models.py:386)
2. `FolhaAlteracaoModel.header_json` (infra/persistence/models.py:608) —
   acompanhado de nota sobre `part1_json`/`part2_json` (linhas 609-610) por
   poderem conter `secoes`/`responsaveis` internos.
3. `SicapexImportFileModel.parsed_json` (infra/persistence/models.py:916)

Nenhuma acao de schema foi tomada. Recomenda-se inspecionar uma amostra real
de cada campo (via `sqlite3` local) antes de decidir promover algum subcampo
a coluna dedicada com migration propria.

## 3. Contagem final

- Colunas `String` sem `length=` explicito: **49** no total
  - 37 sao PK/FK de identificadores UUID (secao 1.1) — recomendacao uniforme `String(36)`.
  - 12 sao campos de negocio/conteudo sem FK (secao 1.2) — tamanho recomendado caso a caso.
- Colunas `JSON`: **24** no total
  - 21 avaliadas como uso legitimo (snapshot/payload/auditoria/conteudo de documento).
  - 3 marcadas como suspeitas para revisao futura (secao 2.1): `ficha_cadastro_json`, `header_json`, `parsed_json`.
- Nenhum outro `models.py` com tabelas SQLAlchemy encontrado fora de
  `infra/persistence/models.py` (modulos em `modules/*/` so contem schemas
  Pydantic, sem `mapped_column`/`Column`/`__tablename__`).
