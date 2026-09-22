"""Cliente da API do Lichess: a única fronteira com o mundo externo.

O acesso ao Lichess passa por uma porta (:class:`Lichess`). Há duas
implementações: :class:`HttpLichess`, que fala HTTP de verdade, e o adaptador
de fixtures nos testes, que lê respostas gravadas da API real. Nenhum teste
toca a rede.

A descoberta é feita em dois passos: os endpoints de lista (``/api/team/...`` e
``/api/user/...``) devolvem apenas os ids; os metadados de cada torneio — e a
contagem de partidas, que só existe no detalhe — vêm de ``/api/tournament/{id}``.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

__all__ = ["Arena", "HttpLichess", "Lichess", "LichessError", "Standing"]

BASE_URL = "https://lichess.org"
DEFAULT_MIN_INTERVAL = 1.0
DEFAULT_MAX_ATTEMPTS = 3
RETRY_AFTER_FALLBACK = 60.0


class LichessError(RuntimeError):
    """Falha ao falar com a API do Lichess."""


@dataclass(frozen=True)
class Arena:
    """Um torneio do Lichess, normalizado a partir do detalhe da API.

    Os testes não montam isto a partir de JSON inventado à mão: o normal é vir
    de :meth:`Arena.from_detail` sobre uma resposta gravada. As bordas ausentes
    do histórico real (zero partidas, menos de dois jogadores) são derivadas de
    um ``Arena`` real com ``dataclasses.replace``.
    """

    id: str
    full_name: str
    created_by: str
    system: str
    minutes: int
    clock_limit: int
    clock_increment: int
    rated: bool
    variant: str
    starts_at: datetime
    is_finished: bool
    nb_players: int
    games: int
    team_member: str | None
    perf: str

    @classmethod
    def from_detail(cls, payload: Mapping[str, Any]) -> Arena:
        """Normaliza o ``ArenaTournamentFull`` do endpoint de detalhe.

        Aceita também o formato do endpoint de lista (``variant`` e ``perf``
        como objetos, ``startsAt`` em milissegundos, ``status`` numérico), para
        que a mesma leitura sirva quando o detalhe faltar.
        """
        stats = payload.get("stats") or {}
        return cls(
            id=str(payload["id"]),
            full_name=str(payload.get("fullName", "")),
            created_by=str(payload.get("createdBy", "")),
            system=str(payload.get("system", "")),
            minutes=int(payload.get("minutes", 0)),
            clock_limit=int((payload.get("clock") or {}).get("limit", 0)),
            clock_increment=int((payload.get("clock") or {}).get("increment", 0)),
            rated=bool(payload.get("rated", False)),
            variant=_key(payload.get("variant")),
            starts_at=_instant(payload.get("startsAt")),
            is_finished=bool(payload.get("isFinished", payload.get("status") == 30)),
            nb_players=int(payload.get("nbPlayers", 0)),
            games=int(stats.get("games", 0)),
            team_member=_optional_str(payload.get("teamMember")),
            perf=_key(payload.get("perf")),
        )


@dataclass(frozen=True)
class Standing:
    """Uma linha da Classificação final de um torneio."""

    username: str
    rank: int
    score: int
    rating: int | None
    performance: int | None
    title: str | None
    sheet: str

    @property
    def games(self) -> int:
        """A contagem de partidas do jogador, derivada do ``sheet``."""
        return len(self.sheet)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Standing:
        sheet = payload.get("sheet") or {}
        return cls(
            username=str(payload["username"]),
            rank=int(payload["rank"]),
            score=int(payload["score"]),
            rating=_optional_int(payload.get("rating")),
            performance=_optional_int(payload.get("performance")),
            title=_optional_str(payload.get("title")),
            sheet=str(sheet.get("scores", "")),
        )


class Lichess(Protocol):
    """A porta do Lichess: o que a coleta precisa do mundo externo."""

    def team_arena_ids(self, team_id: str, *, max: int = 100) -> list[str]:
        """Ids das arenas relevantes ao time, em ordem cronológica inversa."""
        ...

    def created_arena_ids(self, username: str, *, nb: int | None = None) -> list[str]:
        """Ids das arenas criadas por um usuário, em ordem cronológica inversa."""
        ...

    def arena(self, arena_id: str) -> Arena:
        """Metadados de um torneio, já normalizados."""
        ...

    def standings(self, arena_id: str) -> list[Standing]:
        """A Classificação final, na ordem publicada pelo Lichess."""
        ...

    def games_pgn(self, arena_id: str) -> str:
        """As partidas do torneio em PGN."""
        ...


Transport = Callable[[str, Mapping[str, str]], "tuple[int, str, Mapping[str, str]]"]


def _urlopen(url: str, headers: Mapping[str, str]) -> tuple[int, str, Mapping[str, str]]:
    request = urllib.request.Request(url, headers=dict(headers))
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8"), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace"), dict(error.headers or {})


class HttpLichess:
    """Adaptador de produção: fala HTTP com o Lichess.

    Uma requisição de cada vez (como a API pede), com um intervalo mínimo entre
    elas, e recuo exponencial em ``429`` (respeitando ``Retry-After`` quando
    presente). ``transport``, ``sleep`` e ``clock`` são injetáveis para os testes.
    """

    def __init__(
        self,
        *,
        token: str | None = None,
        min_interval: float = DEFAULT_MIN_INTERVAL,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        transport: Transport = _urlopen,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._token = token
        self._min_interval = min_interval
        self._max_attempts = max_attempts
        self._transport = transport
        self._sleep = sleep
        self._clock = clock
        self._last_call: float | None = None

    def team_arena_ids(self, team_id: str, *, max: int = 100) -> list[str]:
        rows = self._get_ndjson(f"/api/team/{team_id}/arena", {"max": max})
        return [str(row["id"]) for row in rows]

    def created_arena_ids(self, username: str, *, nb: int | None = None) -> list[str]:
        params: dict[str, Any] = {}
        if nb is not None:
            params["nb"] = nb
        rows = self._get_ndjson(f"/api/user/{username}/tournament/created", params)
        return [str(row["id"]) for row in rows]

    def arena(self, arena_id: str) -> Arena:
        payload = json.loads(self._get(f"/api/tournament/{arena_id}", {}))
        return Arena.from_detail(payload)

    def standings(self, arena_id: str) -> list[Standing]:
        rows = self._get_ndjson(f"/api/tournament/{arena_id}/results", {"sheet": "1"})
        return [Standing.from_payload(row) for row in rows]

    def games_pgn(self, arena_id: str) -> str:
        return self._get(
            f"/api/tournament/{arena_id}/games", {}, accept="application/x-chess-pgn"
        )

    def _headers(self, accept: str) -> dict[str, str]:
        headers = {"Accept": accept}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _get(
        self, path: str, params: Mapping[str, Any], *, accept: str = "application/json"
    ) -> str:
        url = BASE_URL + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        for attempt in range(self._max_attempts):
            self._throttle()
            status, body, headers = self._transport(url, self._headers(accept))
            if status == 429:
                if attempt + 1 >= self._max_attempts:
                    raise LichessError(f"limite de requisições (429) em {url}")
                self._sleep(_retry_delay(headers, attempt))
                continue
            if status >= 400:
                detail = body.strip()[:200]
                raise LichessError(f"HTTP {status} em {url}: {detail}")
            return body
        raise LichessError(f"não foi possível obter {url}")  # pragma: no cover

    def _get_ndjson(self, path: str, params: Mapping[str, Any]) -> list[dict[str, Any]]:
        body = self._get(path, params, accept="application/x-ndjson")
        return [json.loads(line) for line in body.splitlines() if line.strip()]

    def _throttle(self) -> None:
        now = self._clock()
        if self._last_call is not None and self._min_interval > 0:
            waited = now - self._last_call
            if waited < self._min_interval:
                self._sleep(self._min_interval - waited)
                now = self._clock()
        self._last_call = now


def _retry_delay(headers: Mapping[str, str], attempt: int) -> float:
    backoff = 2.0**attempt
    return max(_retry_after(headers) or 0.0, backoff)


def _retry_after(headers: Mapping[str, str]) -> float | None:
    for key, value in headers.items():
        if str(key).lower() == "retry-after":
            try:
                return float(value)
            except (TypeError, ValueError):
                return RETRY_AFTER_FALLBACK
    return None


def _key(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("key", ""))
    return str(value or "")


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _instant(value: Any) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    if value is None:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
