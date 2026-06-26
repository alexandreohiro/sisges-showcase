from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest


FIXTURE = Path("data/fixtures/compiler_outputs/1o_sgt_alfa_9990000001.zip")
REQUIRED_FILES = {
    "compiler_run.json",
    "folha_alteracoes.odt",
    "folha_alteracoes.pdf",
    "justificativa.txt",
    "pacote.zip",
    "validacao.txt",
    "variables.json",
}


@pytest.mark.skipif(
    not FIXTURE.exists(),
    reason=(
        "Fixture local gerada manualmente, nao versionada (cai na regra "
        "*.zip do .gitignore - nunca foi auditada para commitar). "
        "Presente so em ambientes de dev que ja rodaram o compilador "
        "contra o caso sintetico 'alfa'."
    ),
)
def test_alfa_compiler_output_fixture_contract():
    with zipfile.ZipFile(FIXTURE) as archive:
        names = set(archive.namelist())
        assert REQUIRED_FILES.issubset(names)
        run = json.loads(archive.read("compiler_run.json").decode("utf-8"))
        variables = json.loads(archive.read("variables.json").decode("utf-8"))
        validacao = archive.read("validacao.txt").decode("utf-8")

    assert run["run_id"]
    assert run["trace_id"]
    assert run["status"] in {"CONCLUIDO", "CONCLUIDO_COM_PENDENCIAS", "FALHOU"}
    assert run["militar_id"]
    assert run["nome"]
    assert run["status"] != "RECEBIDO"
    assert "OK_ALL_MONTHS_PRESENT" in validacao
    assert variables["militar"]["nome_completo"]
    assert variables["eventos_por_mes"]
    assert variables["tempo"]["origem"] in {"SICAPEX_BANCO_SISGES", "CALCULADO_SICAPEX_DB"}

    for events in variables["eventos_por_mes"].values():
        for event in events:
            warnings = set(event.get("warnings") or [])
            assert event.get("titulo") or "WARN_EVENT_TITLE_MISSING" in warnings

    if "WARN_TEMPO_PENDENTE_VALIDACAO" in validacao:
        assert run["status"] == "CONCLUIDO_COM_PENDENCIAS"
