"""Orquestração da coleta.

Descobre os candidatos a Torneio Válido nas **duas fontes** — as arenas do time
e as arenas criadas pelos organizadores configurados —, classifica cada um e
arquiva os válidos: Classificação final, PGN e metadados no schema do spec. Cada
torneio é gravado uma vez; a coleta de rotina nunca sobrescreve o que já existe.
Só um pedido explícito de atualização (``refresh``) rebaixa e reescreve um
torneio. O que não entra — candidato que falha, torneio fora de Temporada,
anomalia de Edição — vai para o relatório de pendências, nunca para o
esquecimento.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .archive import (
    ArchivedStanding,
    ArchivedTournament,
    read_tournaments,
    remove_tournament,
    write_pgn,
    write_report,
    write_tournament,
)
from .config import Config
from .lichess import Arena, Lichess, Standing
from .rules import EXCLUDE, Verdict, classify
from .season import season_of

__all__ = [
    "Candidate",
    "CollectResult",
    "EditionEntry",
    "RefreshResult",
    "assign_editions",
    "collect",
    "discover",
    "refresh",
    "refresh_all",
]


@dataclass(frozen=True)
class Candidate:
    """Um torneio descoberto, com o veredito e de onde ele veio."""

    arena: Arena
    verdict: Verdict
    sources: tuple[str, ...]


@dataclass(frozen=True)
class EditionEntry:
    """O que a numeração de Edição precisa saber de um torneio."""

    id: str
    starts_at: datetime
    name: str
    known: int | None


@dataclass(frozen=True)
class CollectResult:
    """O que uma execução da coleta fez."""

    archived: tuple[str, ...]
    skipped: tuple[str, ...]
    report_entries: int


def discover(config: Config, lichess: Lichess) -> list[Candidate]:
    """Descobre e classifica os candidatos, em ordem determinística por data.

    A varredura cobre as arenas do time e as arenas de cada organizador em
    ``scanCreators`` — o endpoint do time não devolve arenas abertas. Os ids são
    unificados; os metadados vêm do detalhe de cada torneio, que é a única fonte
    da contagem de partidas.
    """
    sources: dict[str, list[str]] = {}

    def collect_ids(arena_ids: list[str], source: str) -> None:
        for arena_id in arena_ids:
            bucket = sources.setdefault(arena_id, [])
            if source not in bucket:
                bucket.append(source)

    collect_ids(lichess.team_arena_ids(config.rules.team), f"team:{config.rules.team}")
    for creator in config.rules.scan_creators:
        collect_ids(lichess.created_arena_ids(creator), f"creator:{creator}")

    candidates = []
    for arena_id, bucket in sources.items():
        arena = lichess.arena(arena_id)
        candidates.append(
            Candidate(
                arena=arena,
                verdict=classify(arena, config.rules),
                sources=tuple(bucket),
            )
        )
    return sorted(
        candidates,
        key=lambda candidate: (candidate.arena.starts_at, candidate.arena.id),
    )


def assign_editions(
    entries: list[EditionEntry], edition_pattern: str
) -> tuple[dict[str, int], list[dict[str, object]]]:
    """Numera as Edições em ordem de data, devolvendo também as anomalias.

    O número lido do nome vence; sem número, a Edição é a última conhecida mais
    um. Colisão com um número já usado ou regressão em relação ao torneio
    anterior por data vira anomalia, mas não interrompe a coleta.
    """
    editions: dict[str, int] = {}
    anomalies: list[dict[str, object]] = []
    first_seen: dict[int, str] = {}
    last = 0
    for entry in sorted(entries, key=lambda item: (item.starts_at, item.id)):
        if entry.known is not None:
            edition = entry.known
        else:
            number = _edition_from_name(entry.name, edition_pattern)
            if number is None:
                edition = last + 1
            else:
                edition = number
                if number in first_seen:
                    anomalies.append(
                        _edition_anomaly(
                            entry,
                            edition,
                            f"número {number} do nome colide com o torneio "
                            f"{first_seen[number]}",
                        )
                    )
                elif number < last:
                    anomalies.append(
                        _edition_anomaly(
                            entry,
                            edition,
                            f"número {number} do nome regride em relação ao "
                            f"torneio anterior ({last})",
                        )
                    )
        editions[entry.id] = edition
        first_seen.setdefault(edition, entry.id)
        last = edition
    return editions, anomalies


def collect(
    config: Config, lichess: Lichess, archive_dir: Path, *, now: datetime | None = None
) -> CollectResult:
    """Arquiva os Torneios Válidos ainda não arquivados e escreve as pendências."""
    moment = now or datetime.now(timezone.utc)
    candidates = discover(config, lichess)
    existing = read_tournaments(archive_dir)

    valid = [candidate for candidate in candidates if candidate.verdict.valid]
    editions, anomalies = assign_editions(
        _edition_entries(valid, existing), config.rules.edition_pattern
    )

    archived: list[str] = []
    for candidate in sorted(valid, key=lambda item: (item.arena.starts_at, item.arena.id)):
        arena = candidate.arena
        if arena.id in existing:
            continue
        standings = lichess.standings(arena.id)
        pgn = lichess.games_pgn(arena.id)
        write_tournament(
            archive_dir,
            _archive(arena, candidate.verdict, editions[arena.id], standings, moment),
        )
        write_pgn(archive_dir, arena.id, pgn)
        archived.append(arena.id)

    entries = _report_entries(candidates, existing, archived, anomalies, config)
    write_report(archive_dir, entries, moment)
    skipped = tuple(sorted(c.arena.id for c in valid if c.arena.id in existing))
    return CollectResult(archived=tuple(archived), skipped=skipped, report_entries=len(entries))


@dataclass(frozen=True)
class RefreshResult:
    """O que uma atualização explícita fez."""

    updated: tuple[str, ...]
    removed: tuple[str, ...]
    missing: tuple[str, ...]


def refresh(
    config: Config,
    lichess: Lichess,
    archive_dir: Path,
    arena_id: str,
    *,
    now: datetime | None = None,
) -> RefreshResult:
    """Reprocessa um torneio arquivado sob demanda.

    Rebaixa os dados de novo e reescreve o arquivo daquele torneio. Um torneio
    que deixou de ser válido — em geral por ter entrado em ``exclude`` — sai do
    arquivo. A Edição é preservada, para uma correção de dados não renumerar a
    série.
    """
    moment = now or datetime.now(timezone.utc)
    existing = read_tournaments(archive_dir)
    if arena_id not in existing:
        return RefreshResult(updated=(), removed=(), missing=(arena_id,))
    if _refresh_one(config, lichess, archive_dir, arena_id, existing[arena_id], moment):
        return RefreshResult(updated=(arena_id,), removed=(), missing=())
    return RefreshResult(updated=(), removed=(arena_id,), missing=())


def refresh_all(
    config: Config, lichess: Lichess, archive_dir: Path, *, now: datetime | None = None
) -> RefreshResult:
    """Reprocessa todos os torneios arquivados."""
    moment = now or datetime.now(timezone.utc)
    existing = read_tournaments(archive_dir)
    updated: list[str] = []
    removed: list[str] = []
    for arena_id, tournament in sorted(existing.items()):
        if _refresh_one(config, lichess, archive_dir, arena_id, tournament, moment):
            updated.append(arena_id)
        else:
            removed.append(arena_id)
    return RefreshResult(updated=tuple(updated), removed=tuple(removed), missing=())


def _refresh_one(
    config: Config,
    lichess: Lichess,
    archive_dir: Path,
    arena_id: str,
    existing: ArchivedTournament,
    moment: datetime,
) -> bool:
    """Atualiza um torneio arquivado; devolve ``True`` se ele ficou no arquivo."""
    arena = lichess.arena(arena_id)
    verdict = classify(arena, config.rules)
    if not verdict.valid:
        remove_tournament(archive_dir, arena_id)
        return False
    standings = lichess.standings(arena_id)
    pgn = lichess.games_pgn(arena_id)
    write_tournament(
        archive_dir, _archive(arena, verdict, existing.edition, standings, moment)
    )
    write_pgn(archive_dir, arena_id, pgn)
    return True


def _edition_entries(
    valid: list[Candidate], existing: dict[str, ArchivedTournament]
) -> list[EditionEntry]:
    entries: dict[str, EditionEntry] = {}
    for tournament in existing.values():
        entries[tournament.id] = EditionEntry(
            tournament.id, tournament.starts_at, tournament.name, tournament.edition
        )
    for candidate in valid:
        arena = candidate.arena
        if arena.id not in entries:
            entries[arena.id] = EditionEntry(
                arena.id, arena.starts_at, arena.full_name, None
            )
    return list(entries.values())


def _archive(
    arena: Arena,
    verdict: Verdict,
    edition: int,
    standings: list[Standing],
    now: datetime,
) -> ArchivedTournament:
    return ArchivedTournament(
        id=arena.id,
        name=arena.full_name,
        edition=edition,
        starts_at=arena.starts_at,
        finishes_at=arena.starts_at + timedelta(minutes=arena.minutes),
        minutes=arena.minutes,
        clock_initial=arena.clock_limit,
        clock_increment=arena.clock_increment,
        perf=arena.perf,
        variant=arena.variant,
        rated=arena.rated,
        created_by=arena.created_by,
        team_member=arena.team_member,
        nb_players=arena.nb_players,
        games=arena.games,
        checks=verdict.passed,
        override=verdict.override,
        fetched_at=now,
        standings=tuple(
            ArchivedStanding(
                username=standing.username,
                rank=standing.rank,
                score=standing.score,
                rating=standing.rating,
                performance=standing.performance,
                games=standing.games,
                title=standing.title,
                sheet=standing.sheet,
            )
            for standing in standings
        ),
    )


def _report_entries(
    candidates: list[Candidate],
    existing: dict[str, ArchivedTournament],
    archived: list[str],
    anomalies: list[dict[str, object]],
    config: Config,
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []

    for candidate in sorted(candidates, key=lambda item: item.arena.id):
        if candidate.verdict.valid or candidate.verdict.override == EXCLUDE:
            continue
        entries.append(
            {
                "kind": "near-miss",
                "tournamentId": candidate.arena.id,
                "name": candidate.arena.full_name,
                "failedChecks": list(candidate.verdict.failed),
                "detail": _detail(candidate.verdict.failed, config),
            }
        )

    arenas = {candidate.arena.id: candidate.arena for candidate in candidates}
    for arena_id in sorted(set(existing) | set(archived)):
        arena = arenas.get(arena_id)
        starts_at = arena.starts_at if arena else existing[arena_id].starts_at
        name = arena.full_name if arena else existing[arena_id].name
        if season_of(starts_at, config.seasons) is not None:
            continue
        entries.append(
            {
                "kind": "outside-season",
                "tournamentId": arena_id,
                "name": name,
                "startsAt": _timestamp(starts_at),
                "detail": "Torneio Válido fora de qualquer Temporada configurada",
            }
        )

    entries.extend(anomalies)
    return entries


def _edition_anomaly(entry: EditionEntry, edition: int, detail: str) -> dict[str, object]:
    return {
        "kind": "edition-anomaly",
        "tournamentId": entry.id,
        "name": entry.name,
        "edition": edition,
        "detail": detail,
    }


def _edition_from_name(name: str, pattern: str) -> int | None:
    match = re.search(pattern, name)
    if match is None:
        return None
    try:
        return int(match.group(1))
    except ValueError:  # pragma: no cover - o validador garante o grupo numérico
        return None


def _detail(failed: tuple[str, ...], config: Config) -> str:
    rules = config.rules
    phrases = {
        "system": "não é uma arena",
        "name": f"nome fora do padrão {rules.name_pattern!r}",
        "variant": f"variante não permitida (permitidas: {', '.join(rules.allowed_variants)})",
        "team": f"arena não é restrita ao time {rules.team!r}",
        "minutes": f"duração diferente de {rules.minutes} minutos",
        "finished": "torneio não finalizado",
        "players": f"menos de {rules.min_players} jogadores",
        "games": "sem partidas",
    }
    return "; ".join(phrases[check] for check in failed)


def _timestamp(instant: datetime) -> str:
    return instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
