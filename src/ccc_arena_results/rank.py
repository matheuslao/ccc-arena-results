"""Ranking: a soma dos melhores N Resultados, com elegibilidade e desempates.

O Ranking é uma leitura de uma janela — uma Temporada ou um Recorte — sobre os
torneios já arquivados. Ele não recalcula o score: usa o Resultado oficial
publicado pelo Lichess. A linha carrega os valores que tornam a ordem
explicável (quantos Resultados contaram, participação, primeiros lugares,
melhor Resultado individual), para a página mostrar o porquê, não só o número.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from math import ceil, floor
from typing import Any

from .aliases import Resolver
from .archive import ArchivedStanding, ArchivedTournament
from .config import Config
from .season import Scope, local_date

__all__ = [
    "BreakdownEntry",
    "Ranking",
    "RankingRow",
    "build",
]

_ROUNDINGS = {"ceil": ceil, "floor": floor, "round": round}

_TIE_ATTRIBUTES = {
    "firstPlaces": "first_places",
    "bestSingleScore": "best_single_score",
    "tournamentsPlayed": "played",
}


@dataclass(frozen=True)
class BreakdownEntry:
    """Um Resultado do jogador no período, e se ele contou."""

    tournament_id: str
    score: int
    counted: bool


@dataclass(frozen=True)
class RankingRow:
    """Uma linha do Ranking."""

    rank: int
    person: str
    usernames: tuple[str, ...]
    total: int
    counted: int
    played: int
    participation: float
    eligible: bool
    first_places: int
    best_single_score: int
    breakdown: tuple[BreakdownEntry, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "person": self.person,
            "usernames": list(self.usernames),
            "total": self.total,
            "counted": self.counted,
            "played": self.played,
            "participation": self.participation,
            "eligible": self.eligible,
            "firstPlaces": self.first_places,
            "bestSingleScore": self.best_single_score,
            "breakdown": [
                {
                    "tournamentId": entry.tournament_id,
                    "score": entry.score,
                    "counted": entry.counted,
                }
                for entry in self.breakdown
            ],
        }


@dataclass(frozen=True)
class Ranking:
    """O Ranking de uma janela, pronto para imprimir ou publicar."""

    season: str
    scope: Scope
    generated_at: datetime
    tournaments_considered: int
    best_n: int
    champion_elected: bool
    rows: tuple[RankingRow, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "season": self.season,
            "scope": {"kind": self.scope.kind, "value": self.scope.value},
            "period": {
                "startsAt": self.scope.starts_at.isoformat(),
                "endsAt": self.scope.ends_at.isoformat(),
            },
            "generatedAt": self.generated_at.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "tournamentsConsidered": self.tournaments_considered,
            "bestN": self.best_n,
            "championElected": self.champion_elected,
            "rows": [row.to_payload() for row in self.rows],
        }

    @property
    def champion(self) -> RankingRow | None:
        """O melhor jogador **elegível**, ou ``None`` se não há campeão.

        Só quem tem Participação suficiente pode receber o título; por isso o
        campeão é o primeiro elegível, não necessariamente o primeiro da tabela.
        """
        if not self.champion_elected:
            return None
        for row in self.rows:
            if row.eligible:
                return row
        return None


def build(
    config: Config,
    tournaments: tuple[ArchivedTournament, ...],
    scope: Scope,
    *,
    now: datetime | None = None,
) -> Ranking:
    """Calcula o Ranking de uma janela a partir dos torneios arquivados."""
    moment = now or datetime.now(timezone.utc)
    considered = [
        tournament
        for tournament in tournaments
        if _in_scope(tournament, scope, config)
    ]

    total_tournaments = len(considered)
    best_n = _best_n(config, total_tournaments)
    aliases = Resolver(config.aliases)
    players = _results_by_person(considered, aliases)

    rows = [
        _row(person, results, total_tournaments, best_n, config, aliases)
        for person, results in players.items()
    ]
    rows.sort(key=lambda row: _order_key(row, config))
    rows = _assign_ranks(rows, config)

    champion_elected = (
        total_tournaments >= config.ranking.min_tournaments_for_champion
        and any(row.eligible for row in rows)
    )
    return Ranking(
        season=scope.season,
        scope=scope,
        generated_at=moment,
        tournaments_considered=total_tournaments,
        best_n=best_n,
        champion_elected=champion_elected,
        rows=tuple(rows),
    )


def _in_scope(tournament: ArchivedTournament, scope: Scope, config: Config) -> bool:
    if tournament.id in config.rules.exclude:
        return False
    day = local_date(tournament.starts_at, config.seasons.timezone)
    return scope.starts_at <= day <= scope.ends_at


def _best_n(config: Config, total_tournaments: int) -> int:
    if total_tournaments <= 0:
        return 0
    best = config.ranking.best_n
    value = int(_ROUNDINGS[best.rounding](best.fraction * total_tournaments))
    return max(1, min(value, total_tournaments))


def _results_by_person(
    tournaments: list[ArchivedTournament],
    aliases: Resolver,
) -> dict[str, list[tuple[ArchivedTournament, ArchivedStanding]]]:
    players: dict[str, list[tuple[ArchivedTournament, ArchivedStanding]]] = {}
    for tournament in tournaments:
        for standing in tournament.standings:
            person = aliases.person(standing.username)
            players.setdefault(person, []).append((tournament, standing))
    return players


def _row(
    person: str,
    results: list[tuple[ArchivedTournament, ArchivedStanding]],
    total_tournaments: int,
    best_n: int,
    config: Config,
    aliases: Resolver,
) -> RankingRow:
    ordered = sorted(
        results, key=lambda item: (-item[1].score, item[0].starts_at, item[0].id)
    )
    counted = min(best_n, len(ordered))
    total = sum(standing.score for _, standing in ordered[:counted])
    played = len(ordered)
    participation = played / total_tournaments if total_tournaments else 0.0
    scores = [standing.score for _, standing in ordered]

    return RankingRow(
        rank=0,
        person=person,
        usernames=aliases.usernames(person),
        total=total,
        counted=counted,
        played=played,
        participation=participation,
        eligible=participation
        >= config.ranking.eligibility.min_participation_fraction,
        first_places=sum(1 for _, standing in ordered if standing.rank == 1),
        best_single_score=max(scores) if scores else 0,
        breakdown=tuple(
            BreakdownEntry(tournament.id, standing.score, index < counted)
            for index, (tournament, standing) in enumerate(ordered)
        ),
    )


def _order_key(row: RankingRow, config: Config) -> tuple[Any, ...]:
    criteria = tuple(
        -getattr(row, _TIE_ATTRIBUTES[name]) for name in config.ranking.tie_break
    )
    return criteria + (row.person,)


def _assign_ranks(rows: list[RankingRow], config: Config) -> list[RankingRow]:
    ranked: list[RankingRow] = []
    previous: tuple[int, ...] | None = None
    current_rank = 0
    for position, row in enumerate(rows, start=1):
        criteria = tuple(
            getattr(row, _TIE_ATTRIBUTES[name]) for name in config.ranking.tie_break
        )
        if criteria != previous:
            current_rank = position
        ranked.append(replace(row, rank=current_rank))
        previous = criteria
    return ranked
