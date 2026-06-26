from __future__ import annotations

import json
import zipfile
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import infra.persistence.models  # noqa: F401
from infra.persistence.db import Base
from infra.persistence.models import MilitarModel
from scripts.inspect_militar_trash_archive import inspect_archive


def _write_archive(path: Path, *, militar_id: int = 77, identidade: str = "TRASH0001") -> None:
    manifest = {
        "schema_version": "sisges-trash-manifest-v1",
        "kind": "MILITAR_HARD_DELETE_ARCHIVE",
        "created_at": "2026-05-25T20:00:00+00:00",
        "militar_id": militar_id,
        "nome_completo": "MILITAR LIXEIRA TESTE",
        "identidade": identidade,
        "archive_filename": path.name,
        "restore_note": "Restauracao tecnica com revisao manual.",
    }
    snapshot = {
        "schema_version": "sisges-militar-deletion-archive-v1",
        "created_at": "2026-05-25T20:00:00+00:00",
        "militar": {
            "id": militar_id,
            "nome_completo": "MILITAR LIXEIRA TESTE",
            "identidade": identidade,
            "ativo": True,
        },
        "deleted_records": {
            "militar_periodo_servico": [{"id": 1, "militar_id": militar_id}],
            "folha_alteracao": [],
        },
        "detached_records": {
            "tarefa": [{"id": 10, "militar_id": militar_id}],
            "compiler_run": [],
        },
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("snapshot.json", json.dumps(snapshot))
        archive.writestr("RESTORE_NOTES.txt", "Dry-run only.\n")


def _session_factory(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'trash.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def test_inspect_militar_trash_archive_generates_restore_plan(tmp_path: Path):
    archive_path = tmp_path / "militar_trash.zip"
    output_json = tmp_path / "inspection.json"
    output_txt = tmp_path / "inspection.txt"
    _write_archive(archive_path)

    session_factory = _session_factory(tmp_path)
    db = session_factory()
    try:
        report = inspect_archive(
            db,
            archive_path,
            output_json=output_json,
            output_txt=output_txt,
        )
    finally:
        db.close()

    assert report["ok"] is True
    assert report["can_restore"] is True
    assert report["conflicts"] == []
    assert report["restore_plan"]["writes_database"] is False
    assert report["restore_plan"]["total_deleted_records"] == 1
    assert report["restore_plan"]["total_detached_records"] == 1
    assert output_json.exists()
    assert output_txt.exists()
    assert "RELATORIO DE INSPECAO DE LIXEIRA DE MILITAR" in output_txt.read_text(encoding="utf-8")


def test_inspect_militar_trash_archive_reports_identity_conflict(tmp_path: Path):
    archive_path = tmp_path / "militar_trash.zip"
    _write_archive(archive_path, militar_id=77, identidade="TRASH0001")

    session_factory = _session_factory(tmp_path)
    db = session_factory()
    try:
        db.add(
            MilitarModel(
                id=1001,
                nome_completo="MILITAR EXISTENTE",
                identidade="TRASH0001",
                ativo=True,
            )
        )
        db.commit()

        report = inspect_archive(db, archive_path)
    finally:
        db.close()

    assert report["ok"] is True
    assert report["can_restore"] is False
    assert report["conflicts"][0]["code"] == "MILITAR_IDENTIDADE_EXISTS"
