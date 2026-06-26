# Checklist MySQL - Backup e Restore SISGES

## Antes da migracao

- Confirmar que o SISGES esta parado ou em janela controlada de manutencao.
- Confirmar que o usuario de backup nao e `root`.
- Confirmar local de destino fora do web root e fora do Git.
- Registrar data, responsavel, host, banco e hash do arquivo final.

## Backup logico

```powershell
mysqldump --single-transaction --routines --triggers --events --default-character-set=utf8mb4 -u sisges_backup -p sisges > D:\backups\sisges\sisges_backup.sql
```

## Hash do backup

```powershell
Get-FileHash D:\backups\sisges\sisges_backup.sql -Algorithm SHA256
```

## Restore em banco de teste

```powershell
mysql -u sisges_migrator -p -e "CREATE DATABASE IF NOT EXISTS sisges_restore_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -u sisges_migrator -p sisges_restore_test < D:\backups\sisges\sisges_backup.sql
```

## Validacao minima apos restore

- Rodar `python -m scripts.check_database_connection --url "mysql+pymysql://..."`.
- Rodar `python -m alembic current`.
- Conferir contagem de tabelas criticas.
- Conferir login de usuario operacional em ambiente isolado.
- Conferir leitura de Gestao de Pessoal, Documentos, Tarefas e Compilador.

## Retencao

- Manter copia local protegida.
- Manter copia externa criptografada.
- Testar restore periodicamente.
- Nunca versionar dump SQL, banco, senha ou artefato de backup.
