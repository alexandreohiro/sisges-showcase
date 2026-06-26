from datetime import date

from modules.compilador.application.reference_folha_pdf_parser import parse_reference_folha_text


FOLHA_TEXT = """
MINISTÉRIO DA DEFESA
EXÉRCITO BRASILEIRO
B ADM QGEX - 001156
FOLHAS DE ALTERAÇÕES
NOME: MILITAR TESTE COMPLETO
POSTO/GRADUAÇÃO: 2º Sgt
QAS/QMS: 5310 - QMS - INTENDÊNCIA
IDENTIDADE: 9990000001
GUARNIÇÃO DE BRASÍLIA
2º Semestre de 2024
CP: PERÍODO: 01/07/2024 a 31/12/2024
1ª PARTE
JULHO:
ALTERAÇÃO DE TESTE
- a 9, BI Nº 52 :
Evento publicado para teste.
AGOSTO:
Sem alterações.
SETEMBRO:
Sem alterações.
OUTUBRO:
Sem alterações.
NOVEMBRO:
Sem alterações.
DEZEMBRO:
Comportamento: EXCEPCIONAL
2ª PARTE
TEMPO COMPUTADO DE EFETIVO SERVIÇO (TC): 00 a 06 m 00 d
TNC: 00 a 00 m 00 d
TSCMM: 16 a 05 m 09 d
TSNR: 01 a 09 m 10 d
TTES: 18 a 02 m 19 d
SIGNATARIO RESPONSAVEL
Cel / S Cmt B Adm QGEx
"""


def test_reference_folha_text_parser_extracts_core_variables():
    result = parse_reference_folha_text(FOLHA_TEXT, page_count=2)

    assert result.is_folha_alteracoes is True
    assert result.nome_completo == "MILITAR TESTE COMPLETO"
    assert result.posto_graduacao == "2º Sgt"
    assert result.periodo_inicio == date(2024, 7, 1)
    assert result.periodo_fim == date(2024, 12, 31)
    assert result.semestre == "2"
    assert result.ano == 2024
    assert "JULHO" in result.meses_detectados
    assert "DEZEMBRO" in result.meses_detectados
    assert result.eventos[0]["titulo"] == "ALTERAÇÃO DE TESTE"
    assert result.comportamento == "EXCEPCIONAL"
    assert result.tempos_segunda_parte["tc"] == "00a06m00d"
    assert result.tempos_segunda_parte["tnc"] == "00a00m00d"
    assert result.tempos_segunda_parte["tscmm"] == "16a05m09d"
    assert result.tempos_segunda_parte["tsnr"] == "01a09m10d"
    assert result.tempos_segunda_parte["ttes"] == "18a02m19d"
    assert result.tempos_segunda_parte["origem"] == "TRANSCRITO_DE_FOLHA_PDF_MEMORIA"
