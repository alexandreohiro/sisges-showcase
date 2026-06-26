from __future__ import annotations

import json
from pathlib import Path
import zipfile

from scripts.secretaria_operacional import (
    run_gerar_checklist,
    run_listar_pendencias,
    run_registrar_entrega,
    run_resumo,
    run_validar_docs,
    run_validar_pacote,
    validate_package,
)


def test_validar_pacote_detecta_zip_valido(tmp_path: Path) -> None:
    package = create_delivery_zip(tmp_path)

    result = run_validar_pacote(tmp_path, package)

    assert result.status == "OK"
    assert result.zip_ok is True
    assert result.prontas == 1
    assert result.revisar == 1
    assert result.bloqueadas == 0
    assert (tmp_path / "data/output/VALIDACAO_PACOTE_REVISADO.json").exists()


def test_validar_pacote_erro_claro_quando_nao_existe(tmp_path: Path) -> None:
    result = validate_package(tmp_path / "ausente.zip")

    assert result.exists is False
    assert result.status == "FAILED"
    assert "Pacote não existe." in result.errors


def test_validar_docs_detecta_docs_existentes(tmp_path: Path) -> None:
    create_operational_docs(tmp_path)

    result = run_validar_docs(tmp_path)

    assert result["status"] == "OK"
    assert (tmp_path / "data/output/VALIDACAO_DOCUMENTACAO_OPERACIONAL.txt").exists()


def test_listar_pendencias_gera_csv(tmp_path: Path) -> None:
    delivery = create_delivery_tree(tmp_path)

    items = run_listar_pendencias(tmp_path, delivery)

    assert items
    assert items[0].codigo == "WARN_TEMPO_PENDENTE_VALIDACAO"
    assert (tmp_path / "data/output/PENDENCIAS_OPERACIONAIS_SECRETARIA.csv").exists()


def test_gerar_checklist_cria_arquivo(tmp_path: Path) -> None:
    delivery = create_delivery_tree(tmp_path)
    create_delivery_zip(tmp_path)

    result = run_gerar_checklist(tmp_path, delivery)

    assert Path(result["txt_path"]).exists()
    assert "MILITAR PRONTO" in Path(result["txt_path"]).read_text(encoding="utf-8")


def test_registrar_entrega_cria_json(tmp_path: Path) -> None:
    package = create_delivery_zip(tmp_path)

    result = run_registrar_entrega(tmp_path, package, "Operador Teste", "Entrega teste")

    assert Path(result["json_path"]).exists()
    payload = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    assert payload["responsavel"] == "Operador Teste"
    assert payload["folhas_prontas"] == 1


def test_resumo_nao_quebra_com_arquivos_existentes(tmp_path: Path) -> None:
    create_operational_docs(tmp_path)
    create_delivery_tree(tmp_path)
    create_delivery_zip(tmp_path)

    result = run_resumo(tmp_path)

    assert result["package"]["zip_ok"] is True
    assert result["docs_ok"] is True


def create_delivery_zip(root: Path) -> Path:
    output = root / "data/output"
    output.mkdir(parents=True, exist_ok=True)
    package = output / "PACOTE_ENTREGA_SECRETARIA_REVISADO.zip"
    entries = {
        "FOLHAS_PRONTAS_ASSINATURA/militar_pronto/folha_alteracoes.odt": "odt",
        "FOLHAS_PRONTAS_ASSINATURA/militar_pronto/folha_alteracoes.pdf": "pdf",
        "FOLHAS_PRONTAS_ASSINATURA/militar_pronto/validacao.txt": "OK_ODT_VALID\n",
        "FOLHAS_PRONTAS_ASSINATURA/militar_pronto/justificativa.txt": "Fonte teste\n",
        "FOLHAS_PRONTAS_ASSINATURA/militar_pronto/variables.json": "{}",
        "FOLHAS_PRONTAS_ASSINATURA/militar_pronto/compiler_run.json": "{}",
        "REVISAR_MANUALMENTE/militar_revisar/folha_alteracoes.odt": "odt",
        "REVISAR_MANUALMENTE/militar_revisar/folha_alteracoes.pdf": "pdf",
        "REVISAR_MANUALMENTE/militar_revisar/validacao.txt": "WARN_TEMPO_PENDENTE_VALIDACAO\n",
        "BLOQUEADAS/": "",
        "HOTFIX_APLICADO/": "",
        "RELATORIOS/RELATORIO_REVISAO_FINAL.txt": "Relatorio\n",
        "RELATORIOS/CHECKLIST_ASSINATURA_REVISADO.txt": "Checklist\n",
        "LOGS/hashes_outputs.json": "{}",
        "AMOSTRA_CONFERENCIA/checklist_amostra.txt": "Amostra\n",
    }
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return package


def create_delivery_tree(root: Path) -> Path:
    base = root / "data/output/entrega_final_revisada"
    ready = base / "FOLHAS_PRONTAS_ASSINATURA/militar_pronto"
    review = base / "REVISAR_MANUALMENTE/militar_revisar"
    sample = base / "AMOSTRA_CONFERENCIA"
    for folder in (ready, review, sample, base / "BLOQUEADAS", base / "RELATORIOS", base / "LOGS"):
        folder.mkdir(parents=True, exist_ok=True)
    write_folha_folder(ready, "MILITAR PRONTO", "0101", "OK_ODT_VALID\n")
    write_folha_folder(review, "MILITAR REVISAR", "0202", "WARN_TEMPO_PENDENTE_VALIDACAO\n")
    (sample / "checklist_amostra.txt").write_text("Amostra\n", encoding="utf-8")
    (base / "RELATORIO_REVISAO_FINAL.txt").write_text("Relatorio\n", encoding="utf-8")
    (base / "CHECKLIST_ASSINATURA_REVISADO.txt").write_text("Checklist\n", encoding="utf-8")
    return base


def write_folha_folder(folder: Path, nome: str, identidade: str, validation: str) -> None:
    variables = {
        "militar": {"nome_completo": nome, "identidade": identidade},
        "periodo": {"semestre": "2"},
    }
    run = {"status": "CONCLUIDO", "nome_militar_snapshot": nome}
    (folder / "variables.json").write_text(json.dumps(variables), encoding="utf-8")
    (folder / "compiler_run.json").write_text(json.dumps(run), encoding="utf-8")
    (folder / "validacao.txt").write_text(validation, encoding="utf-8")
    (folder / "folha_alteracoes.odt").write_text("odt", encoding="utf-8")
    (folder / "folha_alteracoes.pdf").write_text("pdf", encoding="utf-8")
    (folder / "justificativa.txt").write_text("justificativa", encoding="utf-8")
    (folder / "pacote.zip").write_text("zip", encoding="utf-8")


def create_operational_docs(root: Path) -> None:
    docs = root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "COMPILADOR_FOLHAS_ALTERACOES_PROCESSO.md").write_text(
        "\n".join(
            [
                "A dor que o processo resolve",
                "O que é uma Folha de Alterações",
                "Por que não é CRUD",
                "Entradas do processo",
                "SiCaPEx",
                "PDFs de alterações",
                "Modelo ODT oficial",
                "1ª Parte",
                "2ª Parte",
                "Comportamento",
                "Assinatura",
                "Validação",
                "Justificativa",
                "Memória do Compilador",
                "Reprocessamento",
                "Checklist humano",
                "Erros clássicos",
                "Conclusão operacional",
                "validado pela secretaria",
            ]
        ),
        encoding="utf-8",
    )
    (docs / "CHECKLIST_OPERADOR_FOLHAS.md").write_text(
        "Antes da assinatura\nConferir\nFOLHAS_PRONTAS_ASSINATURA\nREVISAR_MANUALMENTE\nBLOQUEADAS\n",
        encoding="utf-8",
    )
    (docs / "FLUXO_RAPIDO_ENTREGA_FOLHAS.md").write_text(
        "Importar\nGerar\nRevisar\nEmpacotar\nassinatura\n",
        encoding="utf-8",
    )
    (docs / "ERROS_E_HOTFIX_FOLHAS.md").write_text(
        "Erro\nCausa\nImpacto\nCorreção\n",
        encoding="utf-8",
    )
