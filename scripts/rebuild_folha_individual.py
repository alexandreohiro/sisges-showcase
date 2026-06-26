from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Reprocessa uma Folha de Alteracoes individual para hotfix.")
    parser.add_argument("--identidade")
    parser.add_argument("--militar-id")
    parser.add_argument("--nome")
    parser.add_argument("--ano", required=True)
    parser.add_argument("--semestre", required=True)
    parser.add_argument("--modelo", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--force-qms")
    parser.add_argument("--force-assinatura-praca", action="store_true")
    parser.add_argument("--force-assinatura-oficial", action="store_true")
    parser.add_argument("--allow-pending-output", action="store_true")
    parser.add_argument("--empty-month-mode", default="BLOCK")
    args = parser.parse_args()

    if not args.identidade and not args.militar_id and not args.nome:
        raise SystemExit("Informe --identidade, --militar-id ou --nome para hotfix individual.")
    if args.force_qms or args.force_assinatura_praca or args.force_assinatura_oficial:
        print("Aviso: flags force-* registradas para hotfix; o gerador atual nao altera dados de origem por override.")

    command = [
        sys.executable,
        "-m",
        "scripts.generate_folhas_alteracoes_batch",
        "--ano",
        str(args.ano),
        "--semestre",
        str(args.semestre),
        "--output",
        str(Path(args.output)),
        "--commit",
        "--limit",
        "1",
        "--empty-month-mode",
        args.empty_month_mode,
    ]
    if args.modelo:
        command.extend(["--modelo", str(Path(args.modelo))])
    if args.allow_pending_output:
        command.append("--allow-pending-output")
    if args.identidade:
        command.extend(["--identidade", args.identidade])
    elif args.militar_id:
        command.extend(["--militar-id", str(args.militar_id)])
    else:
        raise SystemExit("--nome ainda exige selecao manual por identidade ou militar-id no gerador atual.")

    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    print("HOTFIX INDIVIDUAL GERADO")
    print(f"Output: {Path(args.output)}")


if __name__ == "__main__":
    main()
