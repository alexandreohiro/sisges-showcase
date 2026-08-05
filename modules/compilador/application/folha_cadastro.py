"""Cadastro de militares como fonte da verdade do perfil das Folhas.

O PDF de folha/boletim e EVIDENCIA; os campos cadastrais (nome completo,
nome de guerra, posto/graduacao, QAS/QMS, identidade) vem do banco quando
o militar tem historico. A reconciliacao nunca e silenciosa:

- match por IDENTIDADE (chave natural) e, na falta, por nome normalizado;
- encontrado: banco preenche/sobrepoe os campos cadastrais e cada
  divergencia com o PDF vira WARN_*_DIVERGENTE_CADASTRO;
- nao encontrado: perfil segue com os dados do PDF + WARN_MILITAR_SEM_CADASTRO.

Fontes suportadas: SQLite (tabela `militar`, espelho do modelo logico do
SISGES v2 em docs/db/) e CSV (colunas identidade, nome_completo,
nome_guerra, posto_graduacao, qas_qms) para seeds simples.
"""

from __future__ import annotations

import csv
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from modules.compilador.application.folha_models import SicapexProfile
from modules.compilador.application.folha_xml_utils import (
    classify_tipo_militar,
    expand_graduacao,
    format_identity,
    normalize_space,
)

SQLITE_MILITAR_DDL = """
create table if not exists militar (
  identidade text primary key,
  nome_completo text not null,
  nome_guerra text,
  posto_graduacao text,
  qas_qms text,
  ativo integer not null default 1
);
"""


@dataclass(slots=True)
class MilitarCadastro:
    identidade: str
    nome_completo: str
    nome_guerra: str = ""
    posto_graduacao: str = ""
    qas_qms: str = ""


@dataclass(slots=True)
class CadastroMilitares:
    por_identidade: dict[str, MilitarCadastro] = field(default_factory=dict)
    por_nome: dict[str, MilitarCadastro] = field(default_factory=dict)

    def adicionar(self, militar: MilitarCadastro) -> None:
        identidade = _norm_identidade(militar.identidade)
        if identidade:
            self.por_identidade[identidade] = militar
        nome = _norm_nome(militar.nome_completo)
        if nome:
            self.por_nome[nome] = militar

    def buscar(self, *, identidade: str = "", nome_completo: str = "") -> MilitarCadastro | None:
        match = self.por_identidade.get(_norm_identidade(identidade))
        if match:
            return match
        return self.por_nome.get(_norm_nome(nome_completo))

    def __len__(self) -> int:
        return len(self.por_identidade) or len(self.por_nome)


def _norm_identidade(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _norm_nome(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return normalize_space(stripped).upper()


def carregar_cadastro(path: str | Path) -> CadastroMilitares:
    path = Path(path)
    cadastro = CadastroMilitares()
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                cadastro.adicionar(
                    MilitarCadastro(
                        identidade=row.get("identidade", "").strip(),
                        nome_completo=row.get("nome_completo", "").strip(),
                        nome_guerra=row.get("nome_guerra", "").strip(),
                        posto_graduacao=row.get("posto_graduacao", "").strip(),
                        qas_qms=row.get("qas_qms", "").strip(),
                    )
                )
        return cadastro

    con = sqlite3.connect(path)
    try:
        rows = con.execute(
            "select identidade, nome_completo, coalesce(nome_guerra, ''), "
            "coalesce(posto_graduacao, ''), coalesce(qas_qms, '') "
            "from militar where coalesce(ativo, 1) = 1"
        ).fetchall()
    finally:
        con.close()
    for identidade, nome_completo, nome_guerra, posto, qms in rows:
        cadastro.adicionar(
            MilitarCadastro(
                identidade=str(identidade),
                nome_completo=str(nome_completo),
                nome_guerra=str(nome_guerra),
                posto_graduacao=str(posto),
                qas_qms=str(qms),
            )
        )
    return cadastro


def reconciliar_perfil(
    profile: SicapexProfile, cadastro: CadastroMilitares | None
) -> tuple[SicapexProfile, list[str]]:
    """Aplica o cadastro ao perfil extraido do PDF, reportando divergencias."""
    if not cadastro or len(cadastro) == 0:
        return profile, ["WARN_CADASTRO_INDISPONIVEL"]

    match = cadastro.buscar(
        identidade=profile.identidade, nome_completo=profile.nome_completo
    )
    if not match:
        return profile, [
            "WARN_MILITAR_SEM_CADASTRO:"
            f"{profile.identidade or '-'}:{profile.nome_completo[:50] or '-'}"
        ]

    validations = [f"OK_CADASTRO_ENCONTRADO:{_norm_identidade(match.identidade)}"]

    def confere(campo: str, pdf_valor: str, banco_valor: str, normalizador=None) -> None:
        norm = normalizador or (lambda v: _norm_nome(v))
        if pdf_valor and banco_valor and norm(pdf_valor) != norm(banco_valor):
            validations.append(
                f"WARN_{campo}_DIVERGENTE_CADASTRO:pdf={pdf_valor[:40]}:banco={banco_valor[:40]}"
            )

    confere("NOME", profile.nome_completo, match.nome_completo)
    confere("IDENTIDADE", profile.identidade, match.identidade, _norm_identidade)
    confere("GRADUACAO", profile.graduacao_abrev, match.posto_graduacao)
    confere("QMS", profile.qm, match.qas_qms)

    # Banco vence os campos cadastrais (o PDF pode estar desatualizado ou
    # truncado); o nome de guerra so existe no banco.
    profile.nome_completo = match.nome_completo or profile.nome_completo
    profile.nome_guerra = match.nome_guerra or profile.nome_guerra
    if match.posto_graduacao:
        profile.graduacao_abrev = match.posto_graduacao
        profile.graduacao_extenso = expand_graduacao(match.posto_graduacao.lower())
        profile.tipo_militar = classify_tipo_militar(match.posto_graduacao)
    if match.qas_qms:
        profile.qm = match.qas_qms
    if match.identidade:
        profile.identidade = format_identity(match.identidade)

    if profile.nome_guerra and _norm_nome(profile.nome_guerra) not in _norm_nome(
        profile.nome_completo
    ):
        validations.append(
            f"WARN_NOME_GUERRA_FORA_DO_NOME:{profile.nome_guerra[:40]}"
        )
    return profile, validations
