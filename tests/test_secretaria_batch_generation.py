rom __future__ import annotations

from datetime import date
import io
import json
import zipfile

from modules.compilador.application.folha_alteracoes_compiler import (
    CompilerOptions,
    EventBlock,
    SicapexProfile,
    TimeSummary,
    period_bounds,
    render_final_odt,
)
from modules.compilador.application.folhas_batch_generator import (
    FolhaBatchItemResult,
    FolhaBatchResult,
    FolhasAlteracoesBatchGenerator,
    build_batch_txt_report,
    group_events_by_month,
    infer_title_from_event_body,
    repair_event_titles,
    write_simple_pdf_preview,
    write_secretaria_mission_reports,
)


def test_secretaria_generation_renders_required_months_and_no_change_text(tmp_path):
    output = tmp_path / "folha_alteracoes.odt"
    options = CompilerOptions(ano=2025, semestre="2")
    start, end, label = period_bounds(2025, "2")
    assert start == date(2025, 7, 1)
    assert end == date(2025, 12, 31)
    profile = SicapexProfile(
        nome_completo="MILITAR TESTE COMPLETO",
        nome_guerra="TESTE",
        graduacao_abrev="3º Sgt",
        graduacao_extenso="3º Sgt",
        qm="5310 - QMS - INTENDENCIA",
        identidade="010064645-4",
        comportamento="EXCEPCIONAL",
    )
    times = TimeSummary(
        tc="00a06m00d",
        tc_arreg="00a06m00d",
        tc_nao_arreg="00a00m00d",
        tc_transito="00a00m00d",
        tc_instalacao="00a00m00d",
        tnc="00a00m00d",
        tscmm="10a00m00d",
        tssd="00a00m00d",
        tsnr="00a00m00d",
        ttes="10a00m00d",
        origem="SICAPEX_BANCO_SISGES",
        dias_reais_ttes=3600,
        dias_reais_tnc=0,
    )

    render_final_odt(
        output_path=output,
        profile=profile,
        events=[EventBlock(mes="AGOSTO", titulo="ALTERACAO", referencia="- a 1, BI Nº 1 :", corpo="Evento.")],
        times=times,
        period_label=label,
        options=options,
    )

    with zipfile.ZipFile(output) as odt:
        names = set(odt.namelist())
        assert {"content.xml", "styles.xml", "meta.xml", "META-INF/manifest.xml"}.issubset(names)
        content = odt.read("content.xml").decode("utf-8")

    for month in ["JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]:
        assert content.count(month + ":") == 1
    assert "Sem alterações." in content
    assert "MILITAR " in content
    assert '<text:span text:style-name="Bold">TESTE</text:span>' in content
    assert "COMPORTAMENTO: " in content
    assert '<text:span text:style-name="Bold">EXCEPCIONAL</text:span>' in content


def test_secretaria_generation_writes_pdf_and_mission_reports(tmp_path):
    pdf = tmp_path / "folha_alteracoes.pdf"
    write_simple_pdf_preview(
        pdf,
        profile=SicapexProfile(nome_completo="MILITAR TESTE", identidade="010064645-4"),
        period_label="2º SEMESTRE DE 2025",
        validation=["OK_ODT_GERADO"],
    )
    assert pdf.read_bytes().startswith(b"%PDF-")

    result = FolhaBatchResult(
        batch_id="batch-teste",
        ano=2025,
        semestre="2",
        dry_run=False,
        total=1,
        generated_count=1,
        pending_count=1,
        failed_count=0,
        output_dir=str(tmp_path),
        package_path=str(tmp_path / "pacote_geral.zip"),
        items=[
            FolhaBatchItemResult(
                militar_id=1,
                nome="MILITAR TESTE",
                identidade="9990000001",
                status="CONCLUIDO_COM_PENDENCIAS",
                run_id="run-1",
                output_dir=str(tmp_path / "militar"),
                zip_path=str(tmp_path / "militar" / "pacote.zip"),
                warnings=["WARN_TEMPO_PENDENTE_VALIDACAO"],
            )
        ],
    )
    write_secretaria_mission_reports(result, tmp_path)

    assert (tmp_path / "RELATORIO_MISSAO_SECRETARIA.txt").exists()
    assert (tmp_path / "CONTROLE_MISSOES_SECRETARIA.csv").exists()
    assert "MILITAR TESTE" in (tmp_path / "RELATORIO_MISSAO_SECRETARIA.txt").read_text(encoding="utf-8")
    assert "WARN_TEMPO_PENDENTE_VALIDACAO" in build_batch_txt_report(result)


def test_secretaria_group_events_by_month_preserves_empty_months():
    grouped = group_events_by_month(
        [EventBlock(mes="JULHO", titulo="A", referencia="BI", corpo="Corpo")],
        "2",
    )

    assert list(grouped) == ["JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
    assert grouped["JULHO"][0]["titulo"] == "A"
    assert grouped["AGOSTO"] == []
    encoded = json.dumps(grouped, ensure_ascii=False).encode("utf-8")
    assert io.BytesIO(encoded).getvalue()


def test_secretaria_repairs_title_glued_to_previous_event_body():
    events = repair_event_titles(
        [
            EventBlock(
                mes="JULHO",
                titulo="APRESENTACAO",
                referencia="- a 1, BI NÂº 1 :",
                corpo="Texto do primeiro evento. TESTE DE AVALIACAO FISICA - Transcricao",
            ),
            EventBlock(
                mes="JULHO",
                titulo="",
                referencia="- a 2, BI NÂº 2 :",
                corpo="Texto do segundo evento.",
            ),
        ]
    )

    assert events[0].corpo == "Texto do primeiro evento"
    assert events[1].titulo == "TESTE DE AVALIACAO FISICA - Transcricao"


def test_secretaria_does_not_keep_resolved_comportamento_warning():
    generator = object.__new__(FolhasAlteracoesBatchGenerator)
    generator.semestre = "2"

    validation = generator._validation_lines(
        [],
        variables={"pending": ["WARN_COMPORTAMENTO_AUSENTE"]},
        context={"fonte_sicapex": "db", "calculo_pendente_validacao": False},
        events=[EventBlock(mes="JULHO", titulo="A", referencia="BI", corpo="Corpo")],
        profile=SicapexProfile(comportamento="BOM"),
    )

    assert "WARN_COMPORTAMENTO_AUSENTE" not in validation


def test_secretaria_infers_common_administrative_event_titles():
    assert (
        infer_title_from_event_body("O Cmt determinou a conferência da Pasta de Habilitação à Pensão Militar e CADBEN")
        == "PASTA DE HABILITACAO A PENSAO MILITAR E CADBEN - Atualizacao"
    )
    assert infer_title_from_event_body("Realizou a 1ª chamada do 3º Teste de Avaliação Física de 2025") == (
        "TESTE DE AVALIACAO FISICA - Transcricao"
    )
    assert infer_title_from_event_body("solicitou cadastramento de sua escolaridade de nível superior no SiCaPEx") == (
        "ESCOLARIDADE - Cadastramento"
    )
    assert infer_title_from_event_body("Aprovo o parecer médico emitido pelo médico atendente") == (
        "INSPECAO DE SAUDE - Parecer medico"
    )
    assert infer_title_from_event_body("PORTARIA - Concessão de Medalha Militar de Ouro") == (
        "MEDALHA MILITAR - Concessao"
    )
    assert infer_title_from_event_body("Em cumprimento a ordem publicada no BI Nr 060") == (
        "PUBLICACAO EM BOLETIM - Transcricao"
    )
