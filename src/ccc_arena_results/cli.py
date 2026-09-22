"""Interface de linha de comando."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from .archive import read_tournaments
from .config import Config, ConfigError, check, load
from .ingest import Candidate, collect, discover, refresh, refresh_all
from .lichess import HttpLichess
from .rank import Ranking, build, resolve_season, season_scope
from .rules import EXCLUDE, INCLUDE

DEFAULT_CONFIG_DIR = Path("config")
DEFAULT_ARCHIVE_DIR = Path("archive")


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

    discover_command = commands.add_parser(
        "discover", help="descobre e classifica candidatos a Torneio Válido"
    )
    discover_command.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
        help="diretório dos arquivos de configuração (padrão: config)",
    )

    collect_command = commands.add_parser(
        "collect", help="arquiva os Torneios Válidos ainda não arquivados"
    )
    collect_command.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
        help="diretório dos arquivos de configuração (padrão: config)",
    )
    collect_command.add_argument(
        "--archive-dir",
        type=Path,
        default=DEFAULT_ARCHIVE_DIR,
        help="diretório do arquivo canônico (padrão: archive)",
    )

    refresh_command = commands.add_parser(
        "refresh", help="rebaixa e reescreve um torneio arquivado"
    )
    refresh_command.add_argument("tournament_id", help="id do torneio no Lichess")
    refresh_command.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
        help="diretório dos arquivos de configuração (padrão: config)",
    )
    refresh_command.add_argument(
        "--archive-dir",
        type=Path,
        default=DEFAULT_ARCHIVE_DIR,
        help="diretório do arquivo canônico (padrão: archive)",
    )

    refresh_all_command = commands.add_parser(
        "refresh-all", help="reprocessa todos os torneios arquivados"
    )
    refresh_all_command.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
        help="diretório dos arquivos de configuração (padrão: config)",
    )
    refresh_all_command.add_argument(
        "--archive-dir",
        type=Path,
        default=DEFAULT_ARCHIVE_DIR,
        help="diretório do arquivo canônico (padrão: archive)",
    )

    rank_command = commands.add_parser(
        "rank", help="calcula e imprime o Ranking de uma Temporada"
    )
    rank_command.add_argument(
        "--season",
        help="rótulo da Temporada (padrão: a única configurada)",
    )
    rank_command.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
        help="diretório dos arquivos de configuração (padrão: config)",
    )
    rank_command.add_argument(
        "--archive-dir",
        type=Path,
        default=DEFAULT_ARCHIVE_DIR,
        help="diretório do arquivo canônico (padrão: archive)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "config" and args.config_command == "check":
        problems = check(args.config_dir)
        if problems:
            _report_config_problems(problems)
            return 1
        print(f"Configuração ok ({args.config_dir})")
        return 0

    if args.command == "discover":
        config = _load(args.config_dir)
        if config is None:
            return 1
        _print_candidates(discover(config, HttpLichess()))
        return 0

    if args.command == "collect":
        config = _load(args.config_dir)
        if config is None:
            return 1
        result = collect(config, HttpLichess(), args.archive_dir)
        print(
            f"Arquivados: {len(result.archived)} novo(s), "
            f"{len(result.skipped)} já existente(s)"
        )
        for arena_id in result.archived:
            print(f"  + {arena_id}")
        print(f"Pendências: {result.report_entries}")
        return 0

    if args.command == "refresh":
        config = _load(args.config_dir)
        if config is None:
            return 1
        result = refresh(config, HttpLichess(), args.archive_dir, args.tournament_id)
        if result.missing:
            print(f"Torneio não arquivado: {result.missing[0]}", file=sys.stderr)
            return 1
        if result.removed:
            print(f"Removido: {result.removed[0]} (não é mais um Torneio Válido)")
        else:
            print(f"Atualizado: {result.updated[0]}")
        return 0

    if args.command == "refresh-all":
        config = _load(args.config_dir)
        if config is None:
            return 1
        result = refresh_all(config, HttpLichess(), args.archive_dir)
        print(f"Atualizados: {len(result.updated)}; Removidos: {len(result.removed)}")
        for arena_id in result.removed:
            print(f"  - {arena_id}")
        return 0

    if args.command == "rank":
        config = _load(args.config_dir)
        if config is None:
            return 1
        try:
            season = resolve_season(config, args.season)
        except ValueError as error:
            print(error, file=sys.stderr)
            return 1
        tournaments = tuple(read_tournaments(args.archive_dir).values())
        ranking = build(config, tournaments, season_scope(season))
        _print_ranking(ranking, config)
        return 0

    return 2


def _load(config_dir: Path) -> Config | None:
    try:
        return load(config_dir)
    except ConfigError as error:
        _report_config_problems(error.problems)
        return None


def _report_config_problems(problems: list[str]) -> None:
    print("Configuração inválida:", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)


def _print_candidates(candidates: list[Candidate]) -> None:
    valid = sum(1 for candidate in candidates if candidate.verdict.valid)
    total = len(candidates)
    print(f"{total} candidatos ({valid} válidos, {total - valid} inválidos)")
    for candidate in candidates:
        status = "VÁLIDO" if candidate.verdict.valid else "INVÁLIDO"
        line = (
            f"{status:<9}{candidate.arena.id:<9}"
            f"{_timestamp(candidate.arena.starts_at)}  {candidate.arena.full_name}"
        )
        if candidate.verdict.override == INCLUDE:
            line += "  — incluído manualmente"
        elif candidate.verdict.override == EXCLUDE:
            line += "  — excluído manualmente"
        elif candidate.verdict.failed:
            line += f"  — falhou: {', '.join(candidate.verdict.failed)}"
        print(line)


def _print_ranking(ranking: Ranking, config: Config) -> None:
    print(
        f"Temporada {ranking.season} — {ranking.tournaments_considered} torneio(s) "
        f"considerado(s), melhores N = {ranking.best_n}"
    )
    minimum = config.ranking.min_tournaments_for_champion
    champion = ranking.champion
    if champion is not None:
        print(f"Campeão: {champion.person}")
    elif ranking.tournaments_considered < minimum:
        print(f"Campeão: não eleito (mínimo de {minimum} torneios)")
    else:
        print("Campeão: não eleito (nenhum jogador elegível)")
    print(f"{'#':>3}  {'Jogador':<20}{'Total':>7}{'Contados':>10}{'Part.':>7}  "
          f"{'1º':>3}{'Melhor':>8}  Elegível")
    for row in ranking.rows:
        print(
            f"{row.rank:>3}  {row.person:<20}{row.total:>7}"
            f"{f'{row.counted}/{row.played}':>10}{f'{row.participation:.0%}':>7}  "
            f"{row.first_places:>3}{row.best_single_score:>8}  "
            f"{'sim' if row.eligible else 'não'}"
        )


def _timestamp(instant: datetime) -> str:
    return instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
