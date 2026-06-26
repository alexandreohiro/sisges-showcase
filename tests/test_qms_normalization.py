from __future__ import annotations

from shared.utils.qms import normalize_qas_qms_qm_for_header


def test_qms_generic_is_empty():
    result = normalize_qas_qms_qm_for_header("QMG 00-QUALQUER QMG / QUALQUER QMP")
    assert result.display == ""
    assert result.status == "GENERIC_EMPTY"


def test_qms_intendencia_with_prefix():
    assert normalize_qas_qms_qm_for_header("5310 - QMS - INTENDÊNCIA").display == "INTENDÊNCIA"


def test_qms_material_belico_specialization():
    assert (
        normalize_qas_qms_qm_for_header("MATERIAL BÉLICO/MANUTENÇÃO DE VIATURA AUTO").display
        == "MATERIAL BÉLICO"
    )


def test_qms_material_belico_ascii_with_prefix():
    assert (
        normalize_qas_qms_qm_for_header("QMS - MATERIAL BELICO/MANUTENCAO DE VIATURA AUTO").display
        == "MATERIAL BÉLICO"
    )


def test_qms_known_values():
    assert normalize_qas_qms_qm_for_header("INFANTARIA").display == "INFANTARIA"
    assert normalize_qas_qms_qm_for_header("COMUNICAÇÕES").display == "COMUNICAÇÕES"


def test_qms_quadro_especial_with_prefix():
    assert normalize_qas_qms_qm_for_header("5116 - QMS - QUADRO ESPECIAL (QE)").display == "QUADRO ESPECIAL"


def test_qms_unknown_is_pending():
    result = normalize_qas_qms_qm_for_header("texto desconhecido")
    assert result.display == ""
    assert result.status == "PENDING"
