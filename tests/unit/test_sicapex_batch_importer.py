import zipfile

from modules.gestao_pessoal.importadores.sicapex.batch_importer import SicapexBatchImporter
from modules.gestao_pessoal.importadores.sicapex.schemas import SicapexBatchReport


def test_import_zip_does_not_duplicate_uppercase_pdf_on_windows(tmp_path, monkeypatch):
    zip_path = tmp_path / "sicapex.zip"
    with zipfile.ZipFile(zip_path, "w") as zout:
        zout.writestr("SQL/MILITAR TESTE_report_ficha_cadastro.PDF", b"pdf")

    importer = SicapexBatchImporter(dry_run=True)
    captured_names: list[str] = []

    def fake_import_paths(paths, *, source_folder: str):
        captured_names.extend(path.name for path in paths)
        return SicapexBatchReport(
            batch_id="dry-run",
            source_folder=source_folder,
            total_files=len(paths),
        )

    monkeypatch.setattr(importer, "_import_paths", fake_import_paths)

    report = importer.import_zip(zip_path)

    assert report.total_files == 1
    assert captured_names == ["MILITAR TESTE_report_ficha_cadastro.PDF"]
