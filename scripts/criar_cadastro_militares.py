"""Cria/atualiza o cadastro local de militares (SQLite) a partir de CSV.

O cadastro e a fonte da verdade do perfil na reformatacao de folhas
(nome completo, NOME DE GUERRA, posto/graduacao, QAS/QMS). Espelha a
tabela `militar` do modelo logico do SISGES v2 (docs/db/) e sera
substituido pelo Supabase na fase R5.

CSV esperado (com cabecalho):
    identidade,nome_completo,nome_guerra,posto_graduacao,qas_qms

Uso:
    python scripts/criar_cadastro_militares.py --csv militares.csv --db cadastro_militares.db

LGPD: o arquivo gerado contem dados pessoais — manter fora de repositorio
e de diretorios sincronizados; usar apenas na maquina da secretaria.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

from modules.compilador.application.folha_cadastro import SQLITE_MILITAR_DDL


def importar(csv_path: Path, db_path: Path) -> tuple[int, int]:
    con = sqlite3.connect(db_path)
    con.executescript(SQLITE_MILITAR_DDL)
    inseridos = atualizados = 0
    with csv_path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            identidade = (row.get("identidade") or "").strip()
            nome = (row.get("nome_completo") or "").strip()
            if not identidade or not nome:
                continue
            cursor = con.execute(
                "insert into militar (identidade, nome_completo, nome_guerra, posto_graduacao, qas_qms)"
                " values (?, ?, ?, ?, ?)"
                " on conflict(identidade) do update set"
                " nome_completo=excluded.nome_completo,"
                " nome_guerra=excluded.nome_guerra,"
                " posto_graduacao=excluded.posto_graduacao,"
                " qas_qms=excluded.qas_qms",
                (
                    identidade,
                    nome,
                    (row.get("nome_guerra") or "").strip(),
                    (row.get("posto_graduacao") or "").strip(),
                    (row.get("qas_qms") or "").strip(),
                ),
            )
            if cursor.rowcount:
                inseridos += 1
            else:
                atualizados += 1
    con.commit()
    con.close()
    return inseridos, atualizados


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--db", required=True)
    args = parser.parse_args()
    inseridos, atualizados = importar(Path(args.csv), Path(args.db))
    total = sqlite3.connect(args.db).execute("select count(*) from militar").fetchone()[0]
    print(f"Registros processados: {inseridos + atualizados} | total no cadastro: {total}")


if __name__ == "__main__":
    main()
