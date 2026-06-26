# Plano de Evolucao para MySQL e Arquitetura Limpa

## 1. Objetivo

Evoluir o SISGES de uma persistencia local orientada a desenvolvimento para uma base MySQL operacional, auditavel e preparada para uso real da secretaria, sem quebrar o funcionamento atual em SQLite durante a transicao.

O foco nao e trocar apenas a URL do banco. O foco e limpar o contrato de persistencia: modelos, migrations, repositories, transacoes, seeds, auditoria, backup, restore, testes e healthcheck.

Complemento operacional de seguranca:

- `docs/PLANO_MIGRACAO_MYSQL_SEGURA.md`
- `ops/mysql/create_sisges_users.sql`
- `ops/mysql/backup_restore_checklist.md`
- `python -m scripts.check_database_connection --json`

## 2. Estado Atual

Base atual conhecida pelo projeto:

- SQLAlchemy como ORM.
- Alembic para migrations.
- SQLite como padrao local em desenvolvimento.
- `infra/persistence/db.py` ja aceita `DATABASE_URL`.
- Modelos concentrados em `infra/persistence/models.py`.
- Repositories em `infra/persistence/repositories/`.
- Seeds em `infra/persistence/seed.py`.
- Migrations em `migrations/versions/`.

Ponto positivo: a camada ja usa SQLAlchemy e pode evoluir para MySQL sem troca completa de framework.

Risco atual: SQLite tolera comportamentos que MySQL nao tolera da mesma forma, especialmente tipos, constraints, indices, JSON, tamanho de `String`, datas e relacionamentos.

## 3. Regra de Transicao

Durante a migracao:

- SQLite continua funcionando para desenvolvimento local rapido.
- MySQL vira alvo de homologacao e producao.
- Nenhuma migration deve depender de comportamento exclusivo do SQLite.
- Nenhum modulo deve acessar engine/session diretamente fora da camada de persistencia.
- Toda alteracao de schema deve passar por migration Alembic.
- Dados operacionais devem ter backup antes de qualquer migracao real.

## 4. Arquitetura Alvo

Separar responsabilidades:

```text
apps/web/routes
        |
modules/*/application
        |
modules/*/domain
        |
infra/persistence/repositories
        |
infra/persistence/models
        |
MySQL / SQLite
```

Regra:

- `routes` validam entrada, autenticacao e permissao.
- `application` executa caso de uso.
- `domain` define regra e contrato.
- `repositories` traduz regra para persistencia.
- `models` representam tabelas.
- `db.py` cria engine/session.

O objetivo e impedir que regra de negocio fique presa em `models.py` ou SQL solto em rota.

## 5. Fases de Execucao

### Fase 1 - Compatibilidade MySQL Sem Migrar Dados

Tarefas:

1. Criar configuracao oficial:
   - `DATABASE_URL=mysql+pymysql://...`
   - `DATABASE_POOL_SIZE`
   - `DATABASE_POOL_RECYCLE`
   - `DATABASE_ECHO`

2. Ajustar `infra/persistence/db.py`:
   - pool configuravel;
   - `pool_pre_ping=True`;
   - connect args por driver;
   - logs seguros sem expor senha.

3. Adicionar dependencias:
   - `pymysql` ou `mysqlclient`.
   - Preferencia operacional em Windows: `pymysql`.

4. Criar healthcheck de banco:
   - conexao;
   - `SELECT 1`;
   - versao do banco;
   - migration head aplicada.

Criterio:

- Backend sobe com SQLite.
- Backend sobe com MySQL vazio.
- `python -m alembic upgrade head` funciona nos dois.

### Fase 2 - Higiene de Modelos e Tipos

Tarefas:

1. Revisar todos os `String` sem tamanho.
2. Definir tamanho para campos operacionais:
   - identidade;
   - email;
   - username;
   - status;
   - tipo;
   - codigo;
   - caminhos de arquivo.

3. Revisar `Text` vs `String`.
4. Revisar `JSON` para MySQL.
5. Padronizar datas:
   - `created_at`;
   - `updated_at`;
   - datas funcionais;
   - UTC sem timezone no banco ou timezone explicito no contrato.

6. Padronizar nomes de constraints e indices.

Criterio:

- Alembic autogenerate nao mostra diffs inesperados.
- MySQL aceita todos os modelos.
- SQLite continua aceitando.

### Fase 3 - Repositories Como Fronteira Obrigatoria

Tarefas:

1. Mapear acessos diretos a `Session` fora de repositories.
2. Criar repositories faltantes por modulo:
   - gestao_pessoal;
   - documentos;
   - compilador/memoria;
   - tarefas;
   - quadro;
   - auth/acessos;
   - auditoria.

3. Padronizar metodos:
   - `get_by_id`;
   - `list`;
   - `create`;
   - `update`;
   - `delete`;
   - `soft_delete`, quando aplicavel;
   - `hard_delete_with_archive`, quando aplicavel.

4. Impedir regra complexa em rota.

Criterio:

- Rotas chamam services/use cases.
- Services chamam repositories.
- Repositories concentram SQLAlchemy.

### Fase 4 - Migration Real Para MySQL

Tarefas:

1. Congelar escrita no SQLite.
2. Gerar backup:
   - arquivo `.db`;
   - dump logico;
   - hashes dos artefatos.

3. Subir MySQL limpo.
4. Aplicar Alembic:

```bash
python -m alembic upgrade head
```

5. Migrar dados:
   - script de export/import por tabela;
   - preservar IDs;
   - preservar relacionamentos;
   - validar contagem por tabela;
   - validar hashes de arquivos externos.

6. Rodar verificacao:
   - usuarios;
   - permissoes;
   - militares;
   - documentos;
   - tarefas;
   - memoria do compilador;
   - auditoria.

Criterio:

- Contagens batem.
- Login funciona.
- Gestao de Pessoal funciona.
- Compilador encontra memoria.
- Documentos baixam.
- Tarefas preservam vinculos.

### Fase 5 - Testes e Overclock

Testes obrigatorios:

```bash
python -m pytest
python -m ruff check .
python -m alembic upgrade head
```

Testes especificos:

- MySQL vazio.
- MySQL com seed.
- MySQL migrado de SQLite.
- rollback de migration.
- conexoes concorrentes.
- transacao com erro.
- criacao/exclusao de militar.
- criacao/exclusao de usuario.
- auditoria de credenciais.
- compilacao de documento com registros persistidos.
- tarefas vinculadas a militar.

Criterio:

- Nenhum teste depende de ordem global do banco.
- Cada teste cria e limpa seu proprio contexto.
- Erros de integridade sao claros.

### Fase 6 - Operacao e Backup

Definir:

- backup diario MySQL;
- retencao;
- restore testado;
- dump antes de migration;
- rotina de verificacao de integridade;
- healthcheck operacional;
- usuario MySQL com privilegio minimo;
- separacao dev/homolog/prod.

Criterio:

- Dev consegue restaurar uma exclusao indevida.
- Secretaria nao depende de banco local solto.
- Deploy tem caminho de rollback.

## 6. Variaveis de Ambiente Alvo

Exemplo:

```env
DATABASE_URL=mysql+pymysql://sisges_app:senha@127.0.0.1:3306/sisges
DATABASE_POOL_SIZE=10
DATABASE_POOL_RECYCLE=280
DATABASE_ECHO=false
```

Regra:

- Nunca commitar senha.
- Nunca usar usuario `root` na aplicacao.
- Banco de producao deve ter usuario proprio e permissao minima.

## 7. Clean Code na Persistencia

Regras objetivas:

1. Nome de tabela em ingles tecnico ou portugues padronizado, sem mistura casual.
2. Campo de status deve ter enum/constante no dominio.
3. JSON so quando o dado for naturalmente flexivel.
4. Dados pesquisaveis nao devem ficar escondidos em JSON.
5. Deletes sensiveis precisam de politica:
   - soft delete;
   - hard delete com arquivo de recuperacao;
   - auditoria.
6. Repository nao deve retornar model cru quando a aplicacao precisa de DTO.
7. Rota nao deve montar SQL.
8. Service nao deve conhecer detalhe de driver MySQL.

## 8. Riscos Conhecidos

- Diferenca de comportamento entre SQLite e MySQL em `JSON`.
- `String` sem tamanho pode falhar ou virar tipo indesejado.
- Constraints ausentes no SQLite podem aparecer como erro no MySQL.
- Datas podem mudar sem padronizacao de timezone.
- Scripts antigos podem assumir caminho `data/sisges.db`.
- Testes podem passar em SQLite e falhar em MySQL.
- Imports grandes do SiCaPEx podem exigir tuning de pool/transacao.

## 9. Procedimento de Retomada

1. Confirmar branch limpa.
2. Rodar testes atuais com SQLite.
3. Criar banco MySQL local vazio.
4. Configurar `DATABASE_URL`.
5. Rodar Alembic.
6. Rodar seed.
7. Rodar testes criticos.
8. Ajustar models/migrations.
9. Criar script de migracao SQLite para MySQL.
10. Homologar com copia real sanitizada.
11. Congelar janela de migracao.
12. Migrar producao.
13. Validar healthcheck e fluxos principais.

## 10. Criterio Final

A evolucao para MySQL estara pronta quando:

- MySQL for o banco homologado.
- SQLite continuar opcional para desenvolvimento.
- Alembic funcionar limpo.
- Seeds funcionarem.
- Repositories isolarem persistencia.
- Backup e restore estiverem testados.
- Login, Gestao de Pessoal, Compilador, Documentos, Tarefas e Quadro funcionarem sobre MySQL.
- Nenhuma senha ou dado sensivel estiver versionado.
- O operador conseguir usar o SISGES sem depender de arquivo `.db` local.

## 11. Analise Tecnica Para Escala Vertical

Escalar verticalmente significa aumentar capacidade de uma unica instalacao principal: mais CPU, mais RAM, disco mais rapido, pool bem dimensionado, indices corretos e consultas previsiveis. Nao e a mesma coisa que distribuir carga entre varios bancos ou shards.

No estado atual, o SISGES tem uma base boa para evoluir:

- `infra/config.py` centraliza `SISGES_DATABASE_URL`.
- `infra/persistence/db.py` cria a engine em um unico ponto.
- Alembic usa `settings.database_url`.
- Os modelos ja usam SQLAlchemy.
- Existem indices em tabelas operacionais importantes: `militar`, `tarefa`, `compiler_run`, `compiler_file`, `workflow_items`, `notificacao`, `sicapex_import_file` e outras.

Mas ainda ha lacunas antes de tratar MySQL como banco operacional:

- `db.py` ainda nao expoe pool configuravel por ambiente.
- `create_engine` ainda nao usa `pool_pre_ping`, `pool_size`, `max_overflow`, `pool_timeout` e `pool_recycle`.
- `infra/config.py` ainda nao possui variaveis oficiais de pool.
- Varios campos usam `String` sem tamanho explicito, o que precisa ser saneado para MySQL.
- Ha muitos campos `JSON`; isso e aceitavel para snapshots e payloads, mas dados pesquisaveis devem ter coluna propria.
- Imports grandes de SiCaPEx e Compilador podem gerar transacoes longas se nao forem paginados/loteados.
- Dashboard, Militar 360, Tarefas e Memoria do Compilador precisam de consultas com paginacao e filtros indexados.

Conclusao tecnica:

O primeiro ganho de escala nao vem de "ser MySQL". Vem de transformar o acesso ao banco em contrato controlado: pool, indices, paginacao, transacoes curtas, arquivos fora do banco e metricas de lentidao.

## 12. Plano de Escala Vertical MySQL

### 12.1 Perfil de Maquina

Perfil minimo para homologacao local:

- 2 vCPU.
- 4 GB RAM.
- SSD.
- MySQL 8.
- Banco dedicado ao SISGES.

Perfil inicial para operacao real pequena:

- 4 vCPU.
- 8 a 16 GB RAM.
- SSD/NVMe.
- Backup diario.
- Restore testado.
- Monitoramento de CPU, RAM, disco, conexoes e queries lentas.

Perfil vertical ampliado:

- 8 vCPU ou mais.
- 32 GB RAM ou mais.
- NVMe.
- MySQL com buffer pool ajustado.
- Logs e artefatos fora do volume principal do banco.
- Rotina de manutencao de indices e revisao de slow queries.

Regra pratica:

Antes de comprar mais maquina, medir. Se a lentidao vem de query sem indice, aumentar CPU e RAM so esconde o problema por pouco tempo.

### 12.2 Configuracao MySQL Alvo

Parametros base a revisar com o administrador do ambiente:

```ini
[mysqld]
character-set-server=utf8mb4
collation-server=utf8mb4_unicode_ci
default-storage-engine=InnoDB
sql_mode=STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION
innodb_buffer_pool_size=60% a 70% da RAM disponivel para MySQL
innodb_log_file_size=512M ou maior conforme volume de escrita
max_connections=100 a 300 conforme pool real da aplicacao
max_allowed_packet=64M
slow_query_log=ON
long_query_time=1
```

Observacao:

O valor exato de `innodb_buffer_pool_size` depende de a maquina ser dedicada ou compartilhada. Em maquina dedicada, 60% a 70% da RAM para InnoDB costuma ser o ponto inicial. Em maquina compartilhada, precisa ser menor.

### 12.3 Pool da Aplicacao

Variaveis alvo no SISGES:

```env
SISGES_DATABASE_URL=mysql+pymysql://sisges_app:senha@127.0.0.1:3306/sisges
SISGES_DATABASE_POOL_SIZE=10
SISGES_DATABASE_MAX_OVERFLOW=20
SISGES_DATABASE_POOL_TIMEOUT=30
SISGES_DATABASE_POOL_RECYCLE=1800
SISGES_DATABASE_ECHO=false
```

Regra de dimensionamento:

```text
conexoes_possiveis = workers_uvicorn * (pool_size + max_overflow)
```

Esse total precisa ser menor que `max_connections` do MySQL, deixando margem para Alembic, shell administrativo, backup, monitoramento e emergencias.

Exemplo:

```text
4 workers * (10 pool + 20 overflow) = 120 conexoes potenciais
```

Nesse caso, `max_connections=150` pode ficar apertado. Melhor reduzir overflow ou aumentar limite com RAM suficiente.

### 12.4 Consultas Criticas Para Indexar

Gestao de Pessoal:

- busca por `identidade`;
- busca por `nome_completo`;
- filtro por `ativo`;
- filtro por `posto_graduacao`;
- filtro por `secao`;
- filtro por `divisao`, quando existir no modelo de militar;
- ordenacao por hierarquia militar.

Tarefas:

- `status + prioridade`;
- `secao_responsavel + status`;
- `militar_id + status`;
- `responsavel_user_id + status`;
- `prazo + status`;
- `origem_modulo + status`.

Compilador:

- `compiler_run.militar_id + ano + semestre`;
- `compiler_run.tipo_compilacao + status`;
- `compiler_file.role + sha256`;
- `compiler_file.run_id + role`;
- `compiler_validation.run_id + level`;
- `compiler_validation.file_id + code`;
- snapshots por `run_id + created_at`.

Documentos:

- `kind + status`;
- `owner_user_id + created_at`;
- `source_module + created_at`;
- `output_sha256`;
- `trace_id`.

Notificacoes:

- `user_id + lida + created_at`;
- `referencia_tipo + referencia_id`.

Quadro:

- `owner_user_id + updated_at`;
- `visibility + updated_at`.

Regra:

Todo endpoint de listagem que chegar em producao deve ter:

- limite/paginacao;
- filtros explicitos;
- ordenacao previsivel;
- indice cobrindo o filtro principal;
- teste com volume.

### 12.5 Escritas Pesadas

Os fluxos mais perigosos para escala vertical sao:

- importacao SiCaPEx em lote;
- compilacao de folhas em lote;
- geracao de documentos;
- exclusao real com arquivo de recuperacao;
- auditoria de credenciais;
- criacao automatica de tarefas por regra.

Regras:

1. Nao manter transacao aberta enquanto gera PDF/ODT/ZIP.
2. Persistir metadados no banco e arquivos no storage local/controlado.
3. Fazer commit por unidade logica pequena.
4. Usar `flush` apenas quando o ID gerado for necessario.
5. Em importacao grande, processar em lotes.
6. Em erro parcial, registrar pendencia em vez de perder todo o lote.
7. Nunca guardar PDF/ODT/ZIP binario dentro do MySQL como regra geral.

### 12.6 JSON no MySQL

JSON deve continuar existindo para:

- snapshots de compilacao;
- payloads de auditoria;
- diagnosticos;
- dados importados que precisam de rastreabilidade;
- metadados flexiveis.

JSON nao deve ser usado como esconderijo para dado pesquisavel:

- identidade;
- militar_id;
- status;
- ano;
- semestre;
- tipo_documento;
- role de arquivo;
- hashes;
- prazos;
- secoes;
- responsaveis.

Se um dado vira filtro de tela, relatorio ou auditoria frequente, ele precisa virar coluna e indice.

### 12.7 Healthcheck Operacional

O healthcheck de banco precisa responder mais que `SELECT 1`.

Campos recomendados:

```json
{
  "database": {
    "status": "ok",
    "driver": "mysql+pymysql",
    "server_version": "8.0.x",
    "pool": {
      "size": 10,
      "checked_out": 2,
      "overflow": 0
    },
    "migration": {
      "current": "...",
      "head": "...",
      "is_current": true
    },
    "latency_ms": 12
  }
}
```

Em producao, nao expor senha, host interno sensivel ou string completa de conexao.

## 13. Testes de Overclock Para Escala Vertical

Antes de chamar MySQL de pronto, executar testes com massa artificial e massa real sanitizada.

### 13.1 Massa Minima

Criar cenario de teste com:

- 2.000 militares.
- 20.000 tarefas.
- 10.000 notificacoes.
- 5.000 documentos.
- 5.000 runs do Compilador.
- 30.000 arquivos/snapshots/validacoes do Compilador.
- 50 lotes SiCaPEx.
- 100 quadros.

Esses numeros nao sao meta final. Sao limite minimo para revelar N+1, listagem sem paginacao e indice ausente.

### 13.2 Cenarias Obrigatorios

1. Login simultaneo.
2. Abrir Home.
3. Abrir Militar 360.
4. Buscar militar por identidade.
5. Filtrar Gestao de Pessoal por secao e posto.
6. Listar tarefas por secao.
7. Criar tarefa vinculada a militar.
8. Abrir memoria do Compilador.
9. Consultar runs por militar/semestre.
10. Gerar documento com metadados persistidos.
11. Importar lote SiCaPEx.
12. Excluir militar com arquivo de recuperacao.
13. Gerar relatorio operacional.

### 13.3 Metricas de Aceite

Para operacao diaria:

- p95 de listagens simples abaixo de 500 ms no backend.
- p95 de buscas por identidade abaixo de 200 ms.
- p95 de consultas de tarefas abaixo de 700 ms.
- importacao grande sem travar login e telas de consulta.
- nenhuma rota de listagem sem limite.
- nenhuma query critica com full table scan injustificado.
- CPU abaixo de 70% em carga normal.
- uso de conexoes abaixo de 70% do limite configurado.
- zero deadlocks recorrentes.

### 13.4 Ferramentas

Sem introduzir arquitetura nova, usar:

- `pytest` para testes integrados;
- scripts de seed volumetrico;
- logs de query lenta do MySQL;
- `EXPLAIN` nas consultas criticas;
- healthcheck de pool;
- medicao simples de tempo por endpoint;
- backup e restore cronometrados.

## 14. Backlog Tecnico Para Implementar MySQL Com Escala Vertical

P0 - Preparar o backend:

1. Adicionar variaveis de pool em `infra/config.py`.
2. Ajustar `infra/persistence/db.py` com pool configuravel.
3. Manter SQLite compativel.
4. Adicionar `pool_pre_ping=True` para MySQL.
5. Adicionar dependencia `pymysql`.
6. Criar healthcheck detalhado do banco.

P1 - Sanear modelos:

1. Revisar `String` sem tamanho.
2. Revisar indices compostos.
3. Revisar `JSON` pesquisavel.
4. Padronizar constraints.
5. Garantir nomes de indices estaveis.

P2 - Criar ambiente MySQL:

1. Criar `docker-compose.mysql.yml` ou guia local equivalente.
2. Criar banco `sisges`.
3. Criar usuario `sisges_app`.
4. Rodar Alembic.
5. Rodar seed.
6. Executar testes criticos.

P3 - Migrar dados:

1. Criar script `scripts/export_sqlite_snapshot.py`.
2. Criar script `scripts/import_mysql_snapshot.py`.
3. Validar contagem por tabela.
4. Validar hashes de arquivos externos.
5. Registrar relatorio de migracao.

P4 - Overclock:

1. Criar seed volumetrico.
2. Criar testes de concorrencia.
3. Criar relatorio de p95 por endpoint.
4. Revisar indices com base em slow query log.
5. Ajustar pool e MySQL.

P5 - Operacao:

1. Backup diario.
2. Restore mensal testado.
3. Dump antes de migration.
4. Procedimento de rollback.
5. Checklist de manutencao.
6. Alerta para disco, conexoes e slow queries.
