"""Validacoes de dominio das Folhas de Alteracoes.

Regras de nomenclatura de arquivo conforme Port. 063-DGP/2020 Art. 27 V:
{identidade}_{ano}_{semestre}_{CodOM}.pdf (ex: 9990000001_2024_1_9999.pdf).
"""

from __future__ import annotations

from pathlib import Path
import re


NOME_ARQUIVO_FOLHA_PATTERN = re.compile(r"^\d{10}_\d{4}_[12]_\d{4,6}$")


def validar_nome_arquivo_folha(filename: str) -> bool:
    stem = Path(filename or "").stem
    return bool(NOME_ARQUIVO_FOLHA_PATTERN.match(stem))
