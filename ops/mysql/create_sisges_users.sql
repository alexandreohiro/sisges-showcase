-- SISGES MySQL hardening baseline.
-- Execute como administrador do MySQL apenas no momento de provisionar o banco.
-- Troque CHANGE_ME_* por senhas fortes fora do Git antes de executar.

CREATE DATABASE IF NOT EXISTS sisges
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'sisges_app'@'localhost'
  IDENTIFIED BY 'CHANGE_ME_APP_PASSWORD';

CREATE USER IF NOT EXISTS 'sisges_migrator'@'localhost'
  IDENTIFIED BY 'CHANGE_ME_MIGRATOR_PASSWORD';

CREATE USER IF NOT EXISTS 'sisges_backup'@'localhost'
  IDENTIFIED BY 'CHANGE_ME_BACKUP_PASSWORD';

GRANT SELECT, INSERT, UPDATE, DELETE
  ON sisges.*
  TO 'sisges_app'@'localhost';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, INDEX, REFERENCES
  ON sisges.*
  TO 'sisges_migrator'@'localhost';

GRANT SELECT, LOCK TABLES, SHOW VIEW, TRIGGER
  ON sisges.*
  TO 'sisges_backup'@'localhost';

FLUSH PRIVILEGES;

-- Validacao sugerida:
-- SHOW GRANTS FOR 'sisges_app'@'localhost';
-- SHOW GRANTS FOR 'sisges_migrator'@'localhost';
-- SHOW GRANTS FOR 'sisges_backup'@'localhost';
