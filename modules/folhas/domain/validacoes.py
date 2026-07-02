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


TOTAIS_OBRIGATORIOS = ("tscmm", "ttes", "tsnr")


def validar_part2_schema(part2: object) -> list[str]:
    """Estrutura minima do Part2Schema (2a Parte revisada pela secretaria).

    Exige objeto com 'totais' contendo tscmm/ttes/tsnr. Nao valida dados
    reais — apenas a completude estrutural exigida antes da ciencia.
    """
    if not isinstance(part2, dict) or not part2:
        return ["part2_json invalido: estrutura vazia ou nao e um objeto."]
    totais = part2.get("totais")
    if not isinstance(totais, dict):
        return ["part2_json invalido: campo obrigatorio 'totais' ausente."]
    erros = [
        f"part2_json invalido: totais.{key} ausente."
        for key in TOTAIS_OBRIGATORIOS
        if key not in totais
    ]
    return erros
