# Plano de Migracao MySQL Segura - SISGES

## 1. Objetivo

Preparar a evolucao do SISGES de SQLite local para MySQL de homologacao/producao com credenciais segregadas, pool de conexao controlado, backup testavel e rastreabilidade operacional.

Esta etapa nao migra dados e nao altera o banco local. Ela cria a base segura para a migracao posterior.

## 2. Principios obrigatorios

- Nao usar usuario `root` pela aplicacao.
- Nao versionar senha, dump, banco, `.env` real ou backup.
- Usar credencial de aplicacao com privilegios minimos.
- Usar credencial separada para Alembic/migrations.
- Usar credencial separada para backup.
- Testar restore antes de qualquer troca operacional.
- Manter SQLite funcional durante a transicao.

## 3. Usuarios MySQL

Arquivo operacional:

```text
ops/mysql/create_sisges_users.sql
```

Usuarios previstos:

- `sisges_app`: usado pelo FastAPI em operacao normal.
- `sisges_migrator`: usado para `alembic upgrade head`.
- `sisges_backup`: usado por `mysqldump`.

Regra:

- `sisges_app` nao deve executar DDL.
- `sisges_migrator` nao deve ser usado no servidor da aplicacao.
- `sisges_backup` nao deve criar, alterar ou excluir dados.

## 4. Variaveis de ambiente

Exemplo sem segredo real:

```env
SISGES_ENV=prod
SISGES_DATABASE_URL=mysql+pymysql://sisges_app:${SISGES_MYSQL_PASSWORD}@127.0.0.1:3306/sisges?charset=utf8mb4
SISGES_DATABASE_POOL_SIZE=5
SISGES_DATABASE_MAX_OVERFLOW=10
SISGES_DATABASE_POOL_RECYCLE_SECONDS=1800
SISGES_DATABASE_POOL_PRE_PING=true
SISGES_DATABASE_ECHO=false
```

Em producao, tambem devem estar ativos:

```env
SISGES_SESSION_COOKIE_SECURE=true
SISGES_SESSION_COOKIE_SAMESITE=strict
SISGES_CSRF_ENABLED=true
SISGES_LOG_FORMAT=json
```

## 5. Validacao de conexao

Antes de tentar conectar, rode o gate estatico de hardening:

```powershell
python -m scripts.mysql_hardening_gate --url "mysql+pymysql://sisges_app:SENHA@127.0.0.1:3306/sisges?charset=utf8mb4" --purpose app --json
```

Para validar a postura defensiva geral do SISGES antes de migrar:

```powershell
python -m scripts.security_preflight --mysql-url "mysql+pymysql://sisges_app:SENHA@127.0.0.1:3306/sisges?charset=utf8mb4" --json
```

Para usuario de migration:

```powershell
python -m scripts.mysql_hardening_gate --url "mysql+pymysql://sisges_migrator:SENHA@127.0.0.1:3306/sisges?charset=utf8mb4" --purpose migration --json
```

Para validar conectividade alem da postura da URL:

```powershell
python -m scripts.mysql_hardening_gate --url "mysql+pymysql://sisges_app:SENHA@127.0.0.1:3306/sisges?charset=utf8mb4" --purpose app --connect --json
```

Comando:

```powershell
python -m scripts.check_database_connection --json
```

Com URL explicita:

```powershell
python -m scripts.check_database_connection --url "mysql+pymysql://sisges_app:SENHA@127.0.0.1:3306/sisges?charset=utf8mb4" --json
```

O comando valida apenas conectividade `SELECT 1`. Ele nao executa migrations e nao altera dados.

## 6. Migrations Alembic

Fluxo recomendado:

1. Criar banco limpo.
2. Aplicar `ops/mysql/create_sisges_users.sql` com senhas fortes.
3. Configurar `.env` temporario com usuario `sisges_migrator`.
4. Rodar:

```powershell
python -m alembic upgrade head
```

5. Trocar `.env` para usuario `sisges_app`.
6. Validar:

```powershell
python -m scripts.check_database_connection --json
python -m infra.persistence.seed
```

## 7. Backup e restore

Checklist operacional:

```text
ops/mysql/backup_restore_checklist.md
```

Regra de aceite:

- backup gerado;
- hash SHA-256 calculado;
- restore testado em banco separado;
- aplicacao sobe contra banco restaurado;
- login e modulos criticos abrem.

## 8. Riscos conhecidos

- MySQL pode expor problemas que SQLite tolera: tamanho de campos, indices, constraints e tipos JSON.
- Rotas antigas podem depender de comportamento permissivo do SQLite.
- Migrations precisam ser testadas em banco limpo antes de usar dados reais.
- Dumps podem conter dados pessoais e devem ser tratados como sensiveis.

## 9. Procedimento de retomada

1. Atualizar dependencias incluindo `pymysql`.
2. Provisionar MySQL local ou servidor de homologacao.
3. Executar SQL de usuarios com senhas reais fora do Git.
4. Rodar `scripts.mysql_hardening_gate` para app e migration.
5. Rodar `scripts.security_preflight`.
6. Rodar `scripts.check_database_connection`.
7. Rodar Alembic com `sisges_migrator`.
8. Rodar `ops/mysql/verify_grants.sql`.
9. Rodar seed e testes criticos.
10. Validar frontend contra backend usando MySQL.
11. Gerar backup e testar restore.
12. Somente depois, planejar migracao de dados SQLite para MySQL.
