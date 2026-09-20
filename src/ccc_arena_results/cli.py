"""Interface de linha de comando."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import check

DEFAULT_CONFIG_DIR = Path("config")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ccc-arena",
        description="Acompanhamento da Temporada da Arena dos Cavaleiros.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    config = commands.add_parser("config", help="operações de configuração")
    config_commands = config.add_subparsers(dest="config_command", required=True)

    check_command = config_commands.add_parser(
        "check", help="valida os arquivos de configuração"
    )
    check_command.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
        help="diretório dos arquivos de configuração (padrão: config)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "config" and args.config_command == "check":
        problems = check(args.config_dir)
        if problems:
            print("Configuração inválida:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        print(f"Configuração ok ({args.config_dir})")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
