-- Verificacao manual de grants MySQL SISGES.
-- Executar apos ops/mysql/create_sisges_users.sql.

SHOW GRANTS FOR 'sisges_app'@'localhost';
SHOW GRANTS FOR 'sisges_migrator'@'localhost';
SHOW GRANTS FOR 'sisges_backup'@'localhost';

SELECT user, host, account_locked
FROM mysql.user
WHERE user IN ('sisges_app', 'sisges_migrator', 'sisges_backup');
