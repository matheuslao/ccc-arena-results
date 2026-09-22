"""Testes do cliente do Lichess e da normalização de um torneio."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ccc_arena_results.lichess import Arena, HttpLichess, LichessError
from lichess_fixtures import FIXTURES


def _payload(arena_id: str) -> dict[str, Any]:
    path = FIXTURES / f"arena_{arena_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_normaliza_o_detalhe_de_uma_fixture_real() -> None:
    arena = Arena.from_detail(_payload("BvMsByPD"))

    assert arena.id == "BvMsByPD"
    assert arena.full_name == "Arena dos Cavaleiros 16a ed. Arena"
    assert arena.created_by == "matheuslao"
    assert arena.system == "arena"
    assert arena.minutes == 60
    assert arena.clock_limit == 300
    assert arena.clock_increment == 2
    assert arena.rated is True
    assert arena.variant == "standard"
    assert arena.starts_at.isoformat() == "2026-09-20T22:00:00+00:00"
    assert arena.is_finished is True
    assert arena.nb_players == 12
    assert arena.games == 26
    assert arena.team_member == "cavaleiros-do-centro"
    assert arena.perf == "blitz"


def test_arena_aberta_nao_tem_time() -> None:
    assert Arena.from_detail(_payload("KPfmJoD9")).team_member is None


def _transport(responses: list[tuple[int, str, dict[str, str]]]):
    calls: list[str] = []

    def send(url: str, headers: Any) -> tuple[int, str, dict[str, str]]:
        calls.append(url)
        return responses.pop(0)

    return send, calls


def test_standings_derivam_as_partidas_do_sheet() -> None:
    body = (FIXTURES / "results_BvMsByPD.ndjson").read_text(encoding="utf-8")
    send, calls = _transport([(200, body, {})])
    client = HttpLichess(transport=send, sleep=lambda _: None, min_interval=0)

    standings = client.standings("BvMsByPD")

    assert standings[0].username == "kleberbios"
    assert standings[0].rank == 1
    assert standings[0].score == 19
    assert standings[0].sheet == "555220"
    assert standings[0].games == 6
    assert any(standing.performance is None for standing in standings)
    assert calls == ["https://lichess.org/api/tournament/BvMsByPD/results?sheet=1"]


def test_games_exportam_o_pgn() -> None:
    pgn = (FIXTURES / "games_BvMsByPD.pgn").read_text(encoding="utf-8")
    seen: dict[str, str] = {}

    def send(url: str, headers: Any) -> tuple[int, str, dict[str, str]]:
        seen["url"] = url
        seen["accept"] = headers.get("Accept", "")
        return 200, pgn, {}

    client = HttpLichess(transport=send, sleep=lambda _: None, min_interval=0)

    assert client.games_pgn("BvMsByPD").startswith('[Event "Arena dos Cavaleiros')
    assert seen["url"] == "https://lichess.org/api/tournament/BvMsByPD/games"
    assert seen["accept"] == "application/x-chess-pgn"


def test_ndjson_e_lido_linha_a_linha() -> None:
    body = (FIXTURES / "team_cavaleiros-do-centro.ndjson").read_text(encoding="utf-8")
    send, calls = _transport([(200, body, {})])
    client = HttpLichess(transport=send, sleep=lambda _: None, min_interval=0)

    ids = client.team_arena_ids("cavaleiros-do-centro")

    assert ids[0] == "BvMsByPD"
    assert len(ids) == 12
    assert calls == ["https://lichess.org/api/team/cavaleiros-do-centro/arena?max=100"]


def test_429_recua_exponencialmente_e_tenta_de_novo() -> None:
    sleeps: list[float] = []
    send, calls = _transport([(429, "", {}), (429, "", {}), (200, '{"id":"x"}\n', {})])
    client = HttpLichess(transport=send, sleep=sleeps.append, min_interval=0)

    assert client.created_arena_ids("alguem") == ["x"]
    assert sleeps == [1.0, 2.0]
    assert len(calls) == 3


def test_429_respeita_retry_after() -> None:
    sleeps: list[float] = []
    send, _ = _transport([(429, "", {"Retry-After": "30"}), (200, '{"id":"x"}\n', {})])
    client = HttpLichess(transport=send, sleep=sleeps.append, min_interval=0)

    client.created_arena_ids("alguem")

    assert sleeps == [30.0]


def test_429_persistente_levanta_erro() -> None:
    send, _ = _transport([(429, "", {}), (429, "", {}), (429, "", {})])
    client = HttpLichess(transport=send, sleep=lambda _: None, min_interval=0)

    with pytest.raises(LichessError):
        client.arena("x")


def test_erro_http_vira_lichess_error() -> None:
    send, _ = _transport([(404, "nao existe", {})])
    client = HttpLichess(transport=send, sleep=lambda _: None, min_interval=0)

    with pytest.raises(LichessError, match="404"):
        client.arena("x")


def test_intervalo_minimo_entre_requisicoes() -> None:
    sleeps: list[float] = []
    now = [100.0]

    def clock() -> float:
        return now[0]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    send, _ = _transport([(200, '{"id":"x"}\n', {}), (200, '{"id":"x"}\n', {})])
    client = HttpLichess(transport=send, sleep=sleep, clock=clock, min_interval=1.0)

    client.arena("x")
    client.arena("x")

    assert sleeps == [1.0]
