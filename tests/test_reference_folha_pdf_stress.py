from __future__ import annotations

from pathlib import Path
from time import perf_counter

from modules.compilador.application.reference_folha_pdf_parser import parse_reference_folha_pdf


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _write_minimal_text_pdf(path: Path, lines: list[str]) -> None:
    commands = ["BT", "/F1 10 Tf", "50 760 Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append("0 -14 Td")
        commands.append(f"({_pdf_escape(line)}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1")

    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n",
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        b"5 0 obj << /Length " + str(len(stream)).encode("ascii") + b" >> stream\n" + stream + b"\nendstream endobj\n",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(output))
        output.extend(obj)

    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    path.write_bytes(output)


def _synthetic_folha_lines(index: int) -> list[str]:
    identidade = f"{index:010d}"
    return [
        "MINISTERIO DA DEFESA",
        "EXERCITO BRASILEIRO",
        "FOLHAS DE ALTERACOES",
        f"NOME: MILITAR PDF SINTETICO {index:03d}",
        "POSTO/GRADUACAO: 3 Sgt",
        "QAS/QMS: INFANTARIA",
        f"IDENTIDADE: {identidade}",
        "2 Semestre de 2025",
        "CP: PERIODO: 01/07/2025 a 31/12/2025",
        "1A PARTE",
        "JULHO:",
        "ALTERACAO DE TESTE",
        "- a 9, BI 52 :",
        f"Evento publicado para teste {index:03d}.",
        "AGOSTO:",
        "Sem alteracoes.",
        "SETEMBRO:",
        "Sem alteracoes.",
        "OUTUBRO:",
        "Sem alteracoes.",
        "NOVEMBRO:",
        "Sem alteracoes.",
        "DEZEMBRO:",
        "Sem alteracoes.",
        "Comportamento: EXCEPCIONAL",
        "2A PARTE",
        "TC: 00 a 06 m 00 d",
        "TNC: 00 a 00 m 00 d",
        "TSCMM: 16 a 05 m 09 d",
        "TSNR: 01 a 09 m 10 d",
        "TTES: 18 a 02 m 19 d",
        "SIGNATARIO RESPONSAVEL",
        "Cel / S Cmt B Adm QGEx",
    ]


def test_reference_folha_pdf_parser_handles_synthetic_pdf_burst(tmp_path: Path):
    paths = []
    for index in range(24):
        path = tmp_path / f"folha_sintetica_{index:03d}.pdf"
        _write_minimal_text_pdf(path, _synthetic_folha_lines(index))
        paths.append(path)

    start = perf_counter()
    results = [parse_reference_folha_pdf(path) for path in paths]
    elapsed = perf_counter() - start

    assert elapsed < 20.0
    assert all(result.is_folha_alteracoes for result in results)
    assert all(result.page_count == 1 for result in results)
    assert all(result.semestre == "2" for result in results)
    assert all(result.ano == 2025 for result in results)
    assert all(result.meses_detectados == ["JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"] for result in results)
    assert all(result.eventos and result.eventos[0]["titulo"] == "ALTERACAO DE TESTE" for result in results)
    assert all(result.tempos_segunda_parte["ttes"] == "18a02m19d" for result in results)
    assert [result.identidade for result in results] == [f"{index:010d}" for index in range(24)]
