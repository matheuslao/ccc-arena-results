"""Adaptador de fixtures: o único dublê do Lichess.

Respostas gravadas uma vez da API real e versionadas em
``tests/fixtures/lichess``. Para regravar, com a API no ar:

    curl -s "https://lichess.org/api/team/{teamId}/arena?max=100" \\
        > tests/fixtures/lichess/team_{teamId}.ndjson
    curl -s "https://lichess.org/api/user/{username}/tournament/created?nb=100" \\
        > tests/fixtures/lichess/created_{username}.ndjson
    curl -s "https://lichess.org/api/tournament/{id}" \\
        > tests/fixtures/lichess/arena_{id}.json
    curl -s "https://lichess.org/api/tournament/{id}/results?sheet=1" \\
        > tests/fixtures/lichess/results_{id}.ndjson
    curl -s "https://lichess.org/api/tournament/{id}/games" \\
        > tests/fixtures/lichess/games_{id}.pgn

Convenção dos nomes:

- ``team_<teamId>.ndjson``       — resposta de ``/api/team/{teamId}/arena``
- ``created_<username>.ndjson``  — resposta de ``/api/user/{username}/tournament/created``
- ``arena_<id>.json``            — resposta de ``/api/tournament/{id}``
- ``results_<id>.ndjson``        — resposta de ``/api/tournament/{id}/results?sheet=1``
- ``games_<id>.pgn``             — resposta de ``/api/tournament/{id}/games``

Nenhum teste toca a rede: o adaptador lê só o disco.
"""

from __future__ import annotations

import json
from pathlib import Path

from ccc_arena_results.lichess import Arena, Standing

__all__ = ["FIXTURES", "FixtureLichess"]

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "lichess"


class FixtureLichess:
    """Implementa a porta :class:`~ccc_arena_results.lichess.Lichess` sobre o disco."""

    def __init__(self, root: Path = FIXTURES) -> None:
        self.root = Path(root)

    def team_arena_ids(self, team_id: str, *, max: int = 100) -> list[str]:
        return self._ids(f"team_{team_id}.ndjson")

    def created_arena_ids(self, username: str, *, nb: int | None = None) -> list[str]:
        return self._ids(f"created_{username}.ndjson")

    def arena(self, arena_id: str) -> Arena:
        payload = json.loads(self._read(f"arena_{arena_id}.json"))
        return Arena.from_detail(payload)

    def standings(self, arena_id: str) -> list[Standing]:
        return [
            Standing.from_payload(json.loads(line))
            for line in self._read(f"results_{arena_id}.ndjson").splitlines()
            if line.strip()
        ]

    def games_pgn(self, arena_id: str) -> str:
        return self._read(f"games_{arena_id}.pgn")

    def _ids(self, filename: str) -> list[str]:
        return [
            str(json.loads(line)["id"])
            for line in self._read(filename).splitlines()
            if line.strip()
        ]

    def _read(self, filename: str) -> str:
        return (self.root / filename).read_text(encoding="utf-8")
