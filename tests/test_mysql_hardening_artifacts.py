from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mysql_hardening_artifacts_exist() -> None:
    assert (ROOT / "docs" / "PLANO_MIGRACAO_MYSQL_SEGURA.md").exists()
    assert (ROOT / "ops" / "mysql" / "create_sisges_users.sql").exists()
    assert (ROOT / "ops" / "mysql" / "verify_grants.sql").exists()
    assert (ROOT / "ops" / "mysql" / "backup_restore_checklist.md").exists()
    assert (ROOT / "scripts" / "check_database_connection.py").exists()
    assert (ROOT / "scripts" / "mysql_hardening_gate.py").exists()
    assert (ROOT / ".env.mysql.example").exists()


def test_mysql_user_script_uses_separate_non_root_roles() -> None:
    sql = (ROOT / "ops" / "mysql" / "create_sisges_users.sql").read_text(encoding="utf-8")

    assert "'sisges_app'@'localhost'" in sql
    assert "'sisges_migrator'@'localhost'" in sql
    assert "'sisges_backup'@'localhost'" in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE" in sql
    assert "CHANGE_ME_APP_PASSWORD" in sql


def test_mysql_grants_verification_script_lists_expected_users() -> None:
    sql = (ROOT / "ops" / "mysql" / "verify_grants.sql").read_text(encoding="utf-8")

    assert "SHOW GRANTS FOR 'sisges_app'@'localhost'" in sql
    assert "SHOW GRANTS FOR 'sisges_migrator'@'localhost'" in sql
    assert "SHOW GRANTS FOR 'sisges_backup'@'localhost'" in sql


def test_secure_mysql_plan_mentions_backup_restore_and_no_real_secret() -> None:
    doc = (ROOT / "docs" / "PLANO_MIGRACAO_MYSQL_SEGURA.md").read_text(encoding="utf-8")

    assert "backup" in doc.lower()
    assert "restore" in doc.lower()
    assert "Nao versionar senha" in doc
    assert "SENHA@127.0.0.1" in doc
