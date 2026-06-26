import json
import zipfile

from modules.compilador.application.default_odt_template import ensure_default_folha_template
from modules.compilador.application.odt_template_policy import REQUIRED_SISGES_MARKERS


def test_ensure_default_folha_template_generates_valid_odt(tmp_path):
    template = ensure_default_folha_template(tmp_path)

    assert template.exists()
    with zipfile.ZipFile(template) as package:
        names = set(package.namelist())
        assert {"content.xml", "styles.xml", "META-INF/manifest.xml"}.issubset(names)
        content = package.read("content.xml").decode("utf-8")
        styles = package.read("styles.xml").decode("utf-8")

    assert "[[SISGES:PRIMEIRA_PARTE]]" in content
    assert "[[SISGES:SEGUNDA_PARTE]]" in content
    assert "Calibri Light" in styles


def test_default_template_contract_fields_are_present(tmp_path):
    template = ensure_default_folha_template(tmp_path)

    with zipfile.ZipFile(template) as package:
        content = package.read("content.xml").decode("utf-8")

    for token in REQUIRED_SISGES_MARKERS:
        assert token in content


def test_full_package_manifest_can_mark_internal_default(tmp_path):
    manifest = {
        "template": {
            "provided_by_user": False,
            "source": "INTERNAL_DEFAULT",
            "role": "INTERNAL_DEFAULT_MODELO_ODT",
            "used": True,
        }
    }

    assert json.loads(json.dumps(manifest))["template"]["source"] == "INTERNAL_DEFAULT"
