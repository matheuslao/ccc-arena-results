"""O arquivo canônico: leitura e escrita dos Torneios Válidos e do relatório.

ADR-0001: o Lichess é a nascente, o arquivo é a fonte da verdade. Cada Torneio
Válido é gravado uma vez e nunca sobrescrito por uma coleta de rotina — uma
recoleta não pode desfazer uma correção humana.

Layout em disco::

    <arquivo>/tournaments/<id>.json   o torneio arquivado (schema do spec)
    <arquivo>/pgn/<id>.pgn            as partidas
    <arquivo>/pendencias.json         o relatório de pendências

A escrita só toca o disco quando o conteúdo muda, para que rodar a coleta duas
vezes não altere nada.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "ArchivedStanding",
    "ArchivedTournament",
    "read_report",
    "read_tournaments",
    "remove_tournament",
    "write_pgn",
    "write_report",
    "write_tournament",
]

TOURNAMENTS_DIR = "tournaments"
PGN_DIR = "pgn"
REPORT_FILE = "pendencias.json"


@dataclass(frozen=True)
class ArchivedStanding:
    """Uma linha da Classificação final, como fica no arquivo."""

    username: str
    rank: int
    score: int
    rating: int | None
    performance: int | None
    games: int
    title: str | None
    sheet: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "rank": self.rank,
            "score": self.score,
            "rating": self.rating,
            "performance": self.performance,
            "games": self.games,
            "title": self.title,
            "sheet": self.sheet,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ArchivedStanding:
        sheet = str(payload.get("sheet", ""))
        return cls(
            username=str(payload["username"]),
            rank=int(payload["rank"]),
            score=int(payload["score"]),
            rating=_optional_int(payload.get("rating")),
            performance=_optional_int(payload.get("performance")),
            games=int(payload.get("games", len(sheet))),
            title=_optional_str(payload.get("title")),
            sheet=sheet,
        )


@dataclass(frozen=True)
class ArchivedTournament:
    """Um Torneio Válido arquivado, no schema do spec."""

    id: str
    name: str
    edition: int
    starts_at: datetime
    finishes_at: datetime
    minutes: int
    clock_initial: int
    clock_increment: int
    perf: str
    variant: str
    rated: bool
    created_by: str
    team_member: str | None
    nb_players: int
    games: int
    checks: tuple[str, ...]
    override: str | None
    fetched_at: datetime
    standings: tuple[ArchivedStanding, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": "lichess",
            "name": self.name,
            "edition": self.edition,
            "startsAt": _iso(self.starts_at),
            "finishesAt": _iso(self.finishes_at),
            "minutes": self.minutes,
            "clock": {"initial": self.clock_initial, "increment": self.clock_increment},
            "perf": self.perf,
            "variant": self.variant,
            "rated": self.rated,
            "createdBy": self.created_by,
            "teamMember": self.team_member,
            "nbPlayers": self.nb_players,
            "games": self.games,
            "validation": {"checks": list(self.checks), "override": self.override},
            "fetchedAt": _iso(self.fetched_at),
            "standings": [standing.to_payload() for standing in self.standings],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ArchivedTournament:
        validation = payload.get("validation") or {}
        return cls(
            id=str(payload["id"]),
            name=str(payload["name"]),
            edition=int(payload["edition"]),
            starts_at=_instant(payload["startsAt"]),
            finishes_at=_instant(payload["finishesAt"]),
            minutes=int(payload.get("minutes", 0)),
            clock_initial=int((payload.get("clock") or {}).get("initial", 0)),
            clock_increment=int((payload.get("clock") or {}).get("increment", 0)),
            perf=str(payload.get("perf", "")),
            variant=str(payload.get("variant", "")),
            rated=bool(payload.get("rated", False)),
            created_by=str(payload.get("createdBy", "")),
            team_member=_optional_str(payload.get("teamMember")),
            nb_players=int(payload.get("nbPlayers", 0)),
            games=int(payload.get("games", 0)),
            checks=tuple(str(check) for check in validation.get("checks", [])),
            override=_optional_str(validation.get("override")),
            fetched_at=_instant(payload["fetchedAt"]),
            standings=tuple(
                ArchivedStanding.from_payload(standing)
                for standing in payload.get("standings", [])
            ),
        )


def read_tournaments(archive_dir: Path) -> dict[str, ArchivedTournament]:
    """Todos os Torneios Válidos arquivados, por id."""
    directory = Path(archive_dir) / TOURNAMENTS_DIR
    if not directory.is_dir():
        return {}
    tournaments = {}
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        tournament = ArchivedTournament.from_payload(payload)
        tournaments[tournament.id] = tournament
    return tournaments


def write_tournament(archive_dir: Path, tournament: ArchivedTournament) -> bool:
    """Grava o torneio; devolve ``True`` se o arquivo mudou."""
    path = Path(archive_dir) / TOURNAMENTS_DIR / f"{tournament.id}.json"
    return _write_if_changed(path, _dumps(tournament.to_payload()))


def write_pgn(archive_dir: Path, arena_id: str, pgn: str) -> bool:
    """Grava as partidas; devolve ``True`` se o arquivo mudou."""
    path = Path(archive_dir) / PGN_DIR / f"{arena_id}.pgn"
    return _write_if_changed(path, pgn)


def remove_tournament(archive_dir: Path, arena_id: str) -> bool:
    """Tira o torneio e o PGN do arquivo; devolve ``True`` se algo saiu."""
    directory = Path(archive_dir)
    changed = False
    for path in (
        directory / TOURNAMENTS_DIR / f"{arena_id}.json",
        directory / PGN_DIR / f"{arena_id}.pgn",
    ):
        if path.is_file():
            path.unlink()
            changed = True
    return changed


def read_report(archive_dir: Path) -> dict[str, Any] | None:
    """O relatório de pendências, ou ``None`` se ainda não existe."""
    path = Path(archive_dir) / REPORT_FILE
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_report(
    archive_dir: Path, entries: Sequence[Mapping[str, Any]], generated_at: datetime
) -> bool:
    """Grava o relatório; não reescreve quando as pendências não mudaram.

    O ``generatedAt`` só avança quando há pendência nova, para que uma coleta
    rotineira sem novidade não polua o histórico do git.
    """
    previous = read_report(archive_dir)
    fresh = [dict(entry) for entry in entries]
    if previous is not None and previous.get("entries") == fresh:
        return False
    payload = {"generatedAt": _iso(generated_at), "entries": fresh}
    return _write_if_changed(Path(archive_dir) / REPORT_FILE, _dumps(payload))


def _write_if_changed(path: Path, text: str) -> bool:
    data = text.encode("utf-8")
    if path.is_file() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def _dumps(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _iso(instant: datetime) -> str:
    return instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)
