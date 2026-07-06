from modules.gestao_pessoal.importadores.sicapex.parser import (
    parse_sicapex_text,
    scrub_sensitive,
)


SICAPEX_TEXT = """
FICHA CADASTRO SICAPEX
DADOS PESSOAIS
Nome: B\u00c1RBARA DIZ FERNANDES MARINHO
Sexo: Feminino
Estado Civil: Solteiro
Data Nascimento: 23/08/1998
DADOS FUNCIONAIS
Posto/Grad:
3\u00ba Sgt B\u00c1RBARA DIZ 29/11/2019
QAS/QMS/QM 5310 - QMS - INTEND\u00caNCIA
OM/CODOM: B Adm QGE7x - 001156
Dt Inicio 01/01/2024
Apresenta\u00e7\u00e3o na GU: 02/01/2024
Data de Engajamento: 01/01/2020
Data de Reengajamento: 01/01/2022
Data de Desengajamento: 31/12/2024
Data de Licenciamento: 01/01/2025
Exclus\u00e3o do Servi\u00e7o Ativo: 02/01/2025
Dt \u00daltima 25/12/2022
Tempo de Servi\u00e7o Anterior 01a02m03d
Tempo de Servi\u00e7o P\u00fablico 04a05m06d
Situacao Carreira/Ativo
Situacao Efetivo pronto
Idt 1234567890 Prec-CP: 123456789 CP: 987654
DATAS DE PRACA
Dt Praca Dt Desligamento Tipo de Forca Documento
09/04/2018 - Normal EB BI 200 Aditamento 3
AFASTAMENTOS
Modalidade Qtd Inicio Fim Documento
Ferias 30 01/01/2025 30/01/2025 BI 1
Dispensa como recompensa 8 01/03/2025 08/03/2025 BI 12
JUSTICA E DISCIPLINA
Bom 01/01/2018 BI 10
\u00d3timo 02/02/2023 BI 20
MOVIMENTACOES
001156 B Adm Q2GEx 01/01/2024 31/12/2025 CLASSIFICACAO
SITUACOES REGULAMENTARES
001156 B Adm QGEx EFETIVO PRONTO 01/01/2024 31/12/2025
TEMPO DE SERVICO
Tempo efetivo servi\u00e7o ap\u00f3s a \u00faltima 2.357 dias
TESTES DE APTIDAO
Nenhum registro encontrado.
"""


def test_sicapex_parser_extracts_core_identity_fields():
    record = parse_sicapex_text(SICAPEX_TEXT)

    assert record.nome_completo == "B\u00c1RBARA DIZ FERNANDES MARINHO"
    assert record.posto_grad_abrev == "3\u00ba Sgt"
    assert record.nome_guerra == "B\u00c1RBARA DIZ"
    assert record.qas_qms_qm == "INTEND\u00caNCIA"
    assert record.identidade_militar == "1234567890"
    assert record.data_praca and record.data_praca.isoformat() == "2018-04-09"
    assert record.data_praca.isoformat() != "1998-08-23"
    assert record.tipo_forca == "Normal EB"
    assert record.om_atual_nome == "B Adm QGEx"
    assert record.om_atual_codom == "001156"
    assert record.data_incorporacao and record.data_incorporacao.isoformat() == "2018-04-09"
    assert record.apresentacao_gu and record.apresentacao_gu.isoformat() == "2024-01-02"
    assert record.ultima_promocao and record.ultima_promocao.isoformat() == "2022-12-25"


def test_sicapex_parser_extracts_service_time_fields():
    record = parse_sicapex_text(SICAPEX_TEXT)

    assert record.data_engajamento and record.data_engajamento.isoformat() == "2020-01-01"
    assert record.data_reengajamento and record.data_reengajamento.isoformat() == "2022-01-01"
    assert record.data_desengajamento and record.data_desengajamento.isoformat() == "2024-12-31"
    assert record.data_licenciamento and record.data_licenciamento.isoformat() == "2025-01-01"
    assert record.data_exclusao_servico_ativo
    assert record.data_exclusao_servico_ativo.isoformat() == "2025-01-02"
    assert (
        record.tempo_servico_anterior_anos,
        record.tempo_servico_anterior_meses,
        record.tempo_servico_anterior_dias,
    ) == (1, 2, 3)
    assert (
        record.tempo_servico_publico_anos,
        record.tempo_servico_publico_meses,
        record.tempo_servico_publico_dias,
    ) == (4, 5, 6)
    assert "SiCaPEx" in record.observacoes_calculo


def test_sicapex_parser_extracts_nome_guerra_from_inline_posto_grad():
    record = parse_sicapex_text(
        """
        DADOS PESSOAIS
        Nome: AGNALDO BARCELOS DA SILVA
        DADOS FUNCIONAIS
        Posto/Grad: Maj Nome BARCELOS Dt Turma: 29/11/2008
        Idt 9990000001 Prec-CP: 123456
        DATAS DE PRACA
        Dt Pra\u00e7a Dt Desligamento Tipo de For\u00e7a Documento
        29/11/2008 Normal EB Bol 000
        """
    )

    assert record.posto_grad_abrev == "Maj"
    assert record.nome_guerra == "BARCELOS"
    assert "NOME_GUERRA_INVALIDO" not in record.pending


def test_sicapex_parser_extracts_functional_events_and_time():
    record = parse_sicapex_text(SICAPEX_TEXT)

    assert len(record.afastamentos) >= 1
    assert record.afastamentos[0].modalidade == "Ferias"
    assert record.comportamento_atual
    assert record.comportamento_atual.tipo == "\u00d3TIMO"
    assert len(record.movimentacoes) == 1
    assert len(record.situacoes_regulamentares) == 1
    assert record.tempo_efetivo_servico_apos_ultima == "2357"


def test_sicapex_parser_treats_no_records_as_empty_list():
    record = parse_sicapex_text("AFASTAMENTOS\nNenhum registro encontrado.\n")

    assert record.afastamentos == []


def test_sicapex_parser_ignores_noise_rows_in_service_time_sections():
    record = parse_sicapex_text(
        """
        DADOS PESSOAIS
        Nome: MILITAR TESTE
        DADOS FUNCIONAIS
        Posto/Grad: 3\u00ba Sgt Nome TESTE Dt Turma: 01/01/2020
        QAS/QMS/QM 5310 - QMS - INTEND\u00caNCIA
        Idt 1234567890 Prec-CP: 123456789 CP: 987654
        DATAS DE PRACA
        Dt Praca Dt Desligamento Tipo de Forca Documento
        09/04/2018 - Normal EB BI Nr 1
        TEMPO DE SERVICO
        Desconto de Tempos de Servicos
        Motivo Dt Inicio Dt Termino Tempo Documento
        Nenhum registro encontrado.
        2
        -
        7
        9
        I
        Acrescimos de Tempo de Servico
        Tipo de Servico Dt Inicio Dt Termino Tempo Status Documento
        Nenhum registro encontrado.
        1
        9
        .
        TESTES DE APTIDAO
        Nenhum registro encontrado.
        """
    )

    assert record.desconto_tempo_servico == []
    assert record.acrescimos_tempo_servico == []


def test_sicapex_scrub_sensitive_data_from_reports():
    payload = {
        "nome_completo": "MILITAR TESTE",
        "cpf": "123.456.789-00",
        "endereco": "Rua Restrita",
        "dados_bancarios": {"banco": "001", "conta": "123"},
        "identidade_militar": "1234567890",
    }

    clean = scrub_sensitive(payload)

    assert clean == {
        "nome_completo": "MILITAR TESTE",
        "identidade_militar": "1234567890",
    }
