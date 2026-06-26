from modules.compilador.application.odt_template_policy import validate_no_leftover_placeholders


def test_detects_graduacao_placeholder():
    assert "ERR_TEMPLATE_PLACEHOLDER_LEFTOVER" in validate_no_leftover_placeholders("[GRADUACAO]")


def test_detects_nome_placeholder():
    assert "ERR_TEMPLATE_PLACEHOLDER_LEFTOVER" in validate_no_leftover_placeholders("[NOME]")


def test_detects_periodo_placeholder():
    assert "ERR_TEMPLATE_PLACEHOLDER_LEFTOVER" in validate_no_leftover_placeholders("[PERIODO]")


def test_detects_leftover_sisges_marker():
    assert "ERR_TEMPLATE_PLACEHOLDER_LEFTOVER" in validate_no_leftover_placeholders("[[SISGES:HEADER]]")


def test_detects_leftover_sisges_flag():
    assert "ERR_TEMPLATE_PLACEHOLDER_LEFTOVER" in validate_no_leftover_placeholders("[SISGES_NOME]")


def test_passes_without_leftover_placeholder():
    assert validate_no_leftover_placeholders("conteudo final", "styles final") == [
        "OK_TEMPLATE_PLACEHOLDERS_REPLACED"
    ]
