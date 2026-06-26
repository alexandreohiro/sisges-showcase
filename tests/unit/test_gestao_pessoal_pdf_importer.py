from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import infra.persistence.models  # noqa: F401
from infra.persistence.db import Base
from modules.gestao_pessoal.application.antiguidade import (
    antiguidade_sort_key,
    is_ativo_na_om,
)
from modules.gestao_pessoal.application.pdf_importer import parse_sicapex_text
from modules.gestao_pessoal.application.schemas import MilitarCreate
from modules.gestao_pessoal.infrastructure.repository import GestaoPessoalRepository


SICAPEX_SAMPLE = """
DADOS PESSOAIS
Nome: ALFA ROGÉRIO SILVA SANTOS
Sexo: MASCULINO Estado Civil: CASADO
Escolaridade: Pós Graduação - Especialização Religião: Espírita
Universo: ATIVO Autodeclaraçao Étnico- Indígena
Filiação
BETA ALFA SILVA SANTOS e GAMA ALFA SANTOS
Naturalidade
País: BRASIL UF: SP Cidade: Campinas
Dt Nasc: 07/06/1975 Idade: 50 anos Nacionalidad Brasileiro(a)
Documentos
CPF: 999.000.000-01 Pis/Pasep: 99900000001 RA:
Número: 000000000000 Zona: 000 Seção: 0000
Idt Civil: 0000001 Órgão UF:
Dados Médicos
Tp Sanguíneo: Tipo B Fator RH: Positivo (+) Doador Órgãos: (X)Sim ( )Não
DADOS FUNCIONAIS
Posto/Grad: Cel Nome ROGÉRIO Dt Turma: 01/01/1995
Dt Última 01/01/2022 QAS/QMS/QM 8107 - ARMA DE INFANTARIA
OM Atual
Cmdo: CMP RM: 11ª RM OM/CODOM: B Adm QGEx - 0.01156 Dt Início 01/01/2025
Local da QGEx - Bloco J - 2º piso - SMU - Brasília/DF
Situação do Militar
Situação Carreira/Ativo
Situação Efetivo pronto
Documentos Funcionais
Idt 9990000001 Prec-CP: 00-0000000 CP: 00000-0
Datas de Praça
Dt Praça Dt Desligamento I Tipo de Força Documento
01/01/1995 Normal EB BIE Nr 02, de 01/01/1995 do(a) EsPCEx
"""


SICAPEX_NILTON_COMPLETUDE_SAMPLE = """
FICHA CADASTRO - SiCaPEx
MASCULINO
Escolaridade: Pos Graduacao - Especializacao
Sexo: Estado Civil:
Religiao: Catolica
CASADO
Nome: INDIA CORONEL LIMA
Filiacao
JOSE EXEMPLO LIMA e MARIA EXEMPLO LIMA
Naturalidade
Pais: BRASIL UF: SP Cidade: Campinas
Dt Nasc: 07/02/1980 Idade: 45 anos
Documentos
CPF: 999.000.000-02 Pis/Pasep: 99900000002 RA:
Idt Civil: 0000002 Orgao UF:
Numero: 000000000000 Zona: 000 Secao: 0000
Dados Medicos
Tp Sanguineo: Tipo A Fator RH: Positivo (+) Doador Orgaos: Sim X Nao
Universo: ATIVO Autodeclaracao Etnico- Parda
Nacionalidad Brasileiro(a)
DADOS FUNCIONAIS
OM Atual
Situacao do Militar
Documentos Funcionais
Posto/Grad:
Dt Ultima
Nome Dt Turma:
30/04/2021 QAS/QMS/QM
Cel INDIA 01/01/1995
8107 - ARMA DE INFANTARIA
Cmdo:
Local da
CMP RM: OM/CODOM: Dt Inicio
QGEx - Bloco J - 2o piso - SMU - Brasilia/DF
11a RM B Adm QGEx - 001156 01/01/2025
Situacao Carreira/Ativo Situacao Comandante/Chefe/Diretor de OM valor Unidade - Gu Comum
Idt 9990000002 Prec-CP: 00-0000000 CP: 00000-0
DADOS INDIVIDUAIS
Contatos
E-Mail Pessoal operador.teste@sisges.local
Dados Biometricos
Altur Cabeca Cabelo Olhos Barba Bigode Maos Cutis Sinais Doador
180 Cast Med Ond Cast Cl S rapado morena NAO
Datas de Praca
Dt Praca Dt Desligamento Tipo de Forca Documento
13/02/1993 Normal EB BIE Nr 02, de 13/02/1993 do(a) EsPCEx
AFASTAMENTOS
Modalidade Qtde Dt Inicio Dt Documento
Ferias regulamentares - parcela unica 7 03/01/2026 09/01/2026 BI B Adm QGEx Nr 100, de 30/12/2025
AGREGACOES
Nr Situacao Dt Dt Documento
0031 Art 81, inciso I - for nomeado para 01/02/2017 01/02/2019 PORT Nr 029-DCEM
ALTERACOES
Ano Semestre OM Versao do Arquivo Situacao
2025 1o Semestre B Adm QGEx 1 Alteracoes arquivadas com sucesso
DEPENDENTES
DEPENDENTE EXEMPLO LIMA
Nome: 12/05/2010
CPF: 99900000099 Masculino Filho(a) 0000000003
HABILITACOES
Cursos/Estagios em Organizacoes Militares
Codigo Nome Natureza Tipo OM Turma Mencao Clas Nota
AAAD01 Formacao Curso no EB AMAN 01/01/1995 Muito Bom (MB) 35 8.516
MOVIMENTACOES
REG CODO OM Cidade Dt Inicio Dt Tipo de Situacao
000109 AMAN Resende-RJ 01/01/1995 30/12/1995 Tipo de movimentacao normal Adido aguardando classificacao
PROMOCOES
Tipo Promocao Posto/Grad Dt Promocao Documento
Merecimento Cel 30/04/2021 DOU/29 abr 21
SITUACOES REGULAMENTARES
Codom OM Motivo Situacao Dt Inicio Dt
001156 B Adm QGEx Nomeacao de Comandante de OM Comandante/Chefe/Diretor de OM valor Unidade - Gu Comum 01/01/2025
TEMPO DE SERVICO
Acrescimos de Tempo de Servico
Guarnicao Especial Categoria A 30/01/1998 30/01/2000 731 dias Computado BI GabCmtEx Nr 044
TESTES DE APTIDAO
TAF
No Ano Chamad Dt Mencao Suficiencia Situacao Documento
1o 2026 Suficiente Sem Mencao 1a 26/03/2026 MAIOR DE 50 ANOS
TAT
Ano Mencao Motivo Nao Documento
2025 Excelente BI B Adm QGEx Nr 039, de 20/05/2025
"""


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_parse_sicapex_text_extracts_core_militar_fields():
    result = parse_sicapex_text(SICAPEX_SAMPLE)

    assert result.warnings == []
    assert result.parsed_data["nome_completo"] == "ALFA ROGÉRIO SILVA SANTOS"
    assert result.parsed_data["posto_graduacao"] == "Cel"
    assert result.parsed_data["nome_guerra"] == "ROGÉRIO"
    assert result.parsed_data["om"] == "B Adm QGEx"
    assert result.parsed_data["identidade"] == "9990000001"
    assert result.parsed_data["cpf"] == "999.000.000-01"
    assert result.parsed_data["data_incorporacao"] == "1995-01-01"
    assert result.parsed_data["ativo"] is True
    assert result.parsed_data["ficha_cadastro_json"]["schema_version"] == (
        "sicapex_ficha_cadastro.v1"
    )


def test_parse_sicapex_text_preserves_full_ficha_sections_and_tables():
    result = parse_sicapex_text(SICAPEX_NILTON_COMPLETUDE_SAMPLE)
    ficha = result.parsed_data["ficha_cadastro_json"]

    assert result.warnings == []
    assert result.parsed_data["nome_completo"] == "INDIA CORONEL LIMA"
    assert result.parsed_data["posto_graduacao"] == "Cel"
    assert result.parsed_data["nome_guerra"] == "INDIA"
    assert result.parsed_data["om"] == "B Adm QGEx"
    assert result.parsed_data["identidade"] == "9990000002"
    assert result.parsed_data["cpf"] == "999.000.000-02"
    assert result.parsed_data["data_incorporacao"] == "1993-02-13"
    assert ficha["fields"]["autodeclaracao_etnico_racial"] == "Parda"

    for section_name in (
        "AFASTAMENTOS",
        "AGREGACOES",
        "ALTERACOES",
        "DEPENDENTES",
        "HABILITACOES",
        "MOVIMENTACOES",
        "PROMOCOES",
        "SITUACOES REGULAMENTARES",
        "TEMPO DE SERVICO",
        "TAF",
        "TAT",
    ):
        assert section_name in ficha["sections"]

    assert ficha["tables"]["afastamentos"][0]["data_inicio"] == "2026-01-03"
    assert ficha["tables"]["promocoes"][0]["posto_graduacao"] == "Cel"
    assert ficha["tables"]["taf"][0]["raw"].startswith("1o 2026")


def test_efetivo_om_splits_active_and_inactive_and_orders_by_antiguidade():
    db = _session()
    repo = GestaoPessoalRepository(db)
    repo.create(
        MilitarCreate(
            nome_completo="Segundo Mais Antigo",
            posto_graduacao="Ten Cel",
            om="B Adm QGEx",
            data_incorporacao=date(1990, 1, 1),
            data_nascimento=date(1970, 1, 1),
            situacao_militar="Carreira/Ativo",
            status_servico="Efetivo pronto",
        )
    )
    repo.create(
        MilitarCreate(
            nome_completo="Mais Antigo",
            posto_graduacao="Cel",
            om="B Adm QGEx",
            data_incorporacao=date(1993, 2, 13),
            data_nascimento=date(1975, 1, 1),
            situacao_militar="Carreira/Ativo",
            status_servico="Efetivo pronto",
        )
    )
    repo.create(
        MilitarCreate(
            nome_completo="Inativo Na OM",
            posto_graduacao="Cel",
            om="B Adm QGEx",
            data_incorporacao=date(1980, 1, 1),
            data_nascimento=date(1960, 1, 1),
            situacao_militar="Reserva",
            status_servico="Inativo",
            ativo=False,
        )
    )

    result = repo.list_efetivo_om(om="B Adm QGEx")

    assert [item.nome_completo for item in result["ativos_na_om"]] == [
        "Mais Antigo",
        "Segundo Mais Antigo",
    ]
    assert [item.nome_completo for item in result["inativos_na_om"]] == ["Inativo Na OM"]
    assert is_ativo_na_om(result["ativos_na_om"][0]) is True
    assert antiguidade_sort_key(result["ativos_na_om"][0]) < antiguidade_sort_key(
        result["ativos_na_om"][1]
    )
