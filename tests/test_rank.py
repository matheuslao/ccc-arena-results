"""Testes do Ranking da Temporada — melhores N, elegibilidade e desempates."""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import ccc_arena_results.cli as cli
from ccc_arena_results.archive import ArchivedStanding, ArchivedTournament, read_tournaments
from ccc_arena_results.config import Config, Season, SeasonsConfig, load
from ccc_arena_results.ingest import collect
from ccc_arena_results.rank import build
from ccc_arena_results.season import (
    month_scope,
    resolve_season,
    scope_for,
    semester_scope,
)
from lichess_fixtures import FIXTURES, FixtureLichess

SHIPPED = Path(__file__).resolve().parents[1] / "config"
NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def config() -> Config:
    return load(SHIPPED)


@pytest.fixture
def client() -> FixtureLichess:
    return FixtureLichess(FIXTURES)


def test_ranking_da_temporada_ponta_a_ponta(tmp_path, config, client) -> None:
    config = _september(config)
    collect(config, client, tmp_path, now=NOW)
    tournaments = tuple(read_tournaments(tmp_path).values())

    ranking = build(config, tournaments, scope_for(config), now=NOW)

    assert ranking.tournaments_considered == 1
    assert ranking.best_n == 1
    assert not ranking.champion_elected
    assert len(ranking.rows) == 12

    leader = ranking.rows[0]
    assert leader.person == "kleberbios"
    assert leader.total == 19
    assert leader.counted == 1
    assert leader.played == 1
    assert leader.participation == 1.0
    assert leader.eligible is True
    assert leader.first_places == 1
    assert leader.best_single_score == 19
    assert leader.breakdown[0].tournament_id == "BvMsByPD"
    assert leader.breakdown[0].counted is True

    # Um torneio fora da Temporada (15ª ed., 2026-09-13) não entra.
    assert "Luffytaro" not in {row.person for row in ranking.rows}


def test_empate_oficial_divide_a_posicao(tmp_path, config, client) -> None:
    config = _september(config)
    collect(config, client, tmp_path, now=NOW)
    tournaments = tuple(read_tournaments(tmp_path).values())

    ranking = build(config, tournaments, scope_for(config), now=NOW)
    ranks = {row.person: row.rank for row in ranking.rows}

    assert ranks["joabeuriel"] == ranks["joatan32"] == 4


def test_payload_do_ranking(tmp_path, config, client) -> None:
    config = _september(config)
    collect(config, client, tmp_path, now=NOW)
    tournaments = tuple(read_tournaments(tmp_path).values())

    payload = build(
        config, tournaments, scope_for(config), now=NOW
    ).to_payload()

    assert payload["season"] == "2026"
    assert payload["scope"] == {"kind": "season", "value": "2026"}
    assert payload["period"] == {"startsAt": "2026-09-20", "endsAt": "2026-12-31"}
    assert payload["bestN"] == 1
    assert payload["championElected"] is False
    assert payload["generatedAt"] == "2026-09-22T12:00:00Z"
    assert set(payload["rows"][0]) == {
        "rank",
        "person",
        "usernames",
        "total",
        "counted",
        "played",
        "participation",
        "eligible",
        "firstPlaces",
        "bestSingleScore",
        "breakdown",
    }


def test_melhores_n_e_desempates(config) -> None:
    scenario = _scenario_config(config)
    tournaments = _scenario_tournaments()

    ranking = build(scenario, tournaments, scope_for(scenario), now=NOW)

    assert ranking.tournaments_considered == 4
    assert ranking.best_n == 2
    assert [row.person for row in ranking.rows] == ["A", "D", "F", "G", "B", "C", "H", "I"]
    assert [row.rank for row in ranking.rows] == [1, 2, 3, 4, 5, 6, 7, 7]

    a = _row(ranking, "A")
    assert (a.total, a.counted, a.played, a.participation) == (18, 2, 4, 1.0)
    assert (a.first_places, a.best_single_score, a.eligible) == (4, 10, True)

    # Jogou menos que N: conta tudo o que jogou.
    c = _row(ranking, "C")
    assert (c.total, c.counted, c.played, c.participation, c.eligible) == (3, 1, 1, 0.25, False)

    # Fora de escopo: um torneio excluído e um fora da janela não entram.
    persons = {row.person for row in ranking.rows}
    assert "Excluido" not in persons
    assert "Zed" not in persons
    assert "T5" not in {entry.tournament_id for row in ranking.rows for entry in row.breakdown}


def test_campeao_exige_elegivel(config) -> None:
    scenario = _scenario_config(config)

    ranking = build(scenario, _scenario_tournaments(), scope_for(scenario), now=NOW)

    assert ranking.champion_elected is True
    assert ranking.champion is not None
    assert ranking.champion.person == "A"


def test_campeao_nao_eleito_com_poucos_torneios(tmp_path, config, client) -> None:
    config = _september(config)
    collect(config, client, tmp_path, now=NOW)
    tournaments = tuple(read_tournaments(tmp_path).values())

    ranking = build(config, tournaments, scope_for(config), now=NOW)

    assert ranking.champion_elected is False
    assert ranking.champion is None


def test_resolve_season(config) -> None:
    assert resolve_season(config, None).label == "2026"
    assert resolve_season(config, "2026").label == "2026"
    with pytest.raises(ValueError):
        resolve_season(config, "9999")


def test_mesmo_jogador_em_recortes_diferentes(config) -> None:
    scenario = _scope_config(config)
    tournaments = _scope_tournaments()
    season = resolve_season(scenario, None)

    september = build(scenario, tournaments, month_scope(season, "2026-09"), now=NOW)
    october = build(scenario, tournaments, month_scope(season, "2026-10"), now=NOW)
    semester = build(scenario, tournaments, semester_scope(season, "2026-H2"), now=NOW)

    assert (september.tournaments_considered, september.best_n) == (3, 3)
    assert (october.tournaments_considered, october.best_n) == (1, 1)
    assert (semester.tournaments_considered, semester.best_n) == (5, 4)

    assert september.champion_elected and september.champion.person == "A"
    assert october.champion_elected is False
    assert semester.champion_elected is True

    assert _row(september, "A").counted == 3
    assert _row(october, "A").counted == 1
    assert _row(semester, "A").counted == 4


def test_recorte_no_fuso_de_referencia_na_virada_do_ano(config) -> None:
    season = Season(label="virada", starts_at=date(2026, 12, 1), ends_at=date(2027, 2, 28))
    scenario = dataclasses.replace(
        config,
        seasons=SeasonsConfig(timezone="America/Sao_Paulo", seasons=[season]),
    )
    # 2027-01-01T02:00Z ainda é 2026-12-31 23:00 em São Paulo.
    tournament = _tournament("NY", 1, [("A", 1, 5)], month=1)
    tournament = dataclasses.replace(
        tournament, starts_at=datetime(2027, 1, 1, 2, 0, tzinfo=timezone.utc)
    )

    december = build(scenario, (tournament,), month_scope(season, "2026-12"), now=NOW)
    january = build(scenario, (tournament,), month_scope(season, "2027-01"), now=NOW)

    assert december.tournaments_considered == 1
    assert january.tournaments_considered == 0


def test_cli_rank(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "HttpLichess", lambda: FixtureLichess(FIXTURES))
    archive = tmp_path / "archive"
    cli.main(["collect", "--config-dir", str(SHIPPED), "--archive-dir", str(archive)])
    capsys.readouterr()

    code = cli.main(["rank", "--config-dir", str(SHIPPED), "--archive-dir", str(archive)])
    out = capsys.readouterr().out

    assert code == 0
    assert "Temporada 2026" in out
    assert "melhores N = 9" in out
    assert "kleberbios" in out


def test_cli_rank_de_um_mes(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "HttpLichess", lambda: FixtureLichess(FIXTURES))
    archive = tmp_path / "archive"
    cli.main(["collect", "--config-dir", str(SHIPPED), "--archive-dir", str(archive)])
    capsys.readouterr()

    code = cli.main(
        ["rank", "--month", "2026-09", "--config-dir", str(SHIPPED), "--archive-dir", str(archive)]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "Recorte 2026-09" in out
    assert "2026-09-01 a 2026-09-30" in out


def test_cli_rank_recusa_recorte_fora_da_temporada(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "HttpLichess", lambda: FixtureLichess(FIXTURES))

    code = cli.main(
        ["rank", "--month", "2025-08", "--config-dir", str(SHIPPED), "--archive-dir", str(tmp_path)]
    )

    assert code == 1
    assert "fora da Temporada" in capsys.readouterr().err


def _row(ranking, person: str):
    return next(row for row in ranking.rows if row.person == person)


def _september(config: Config) -> Config:
    """A config real com a Temporada restrita a setembro/2026."""
    seasons = SeasonsConfig(
        timezone="America/Sao_Paulo",
        seasons=[Season(label="2026", starts_at=date(2026, 9, 20), ends_at=date(2026, 12, 31))],
    )
    return dataclasses.replace(config, seasons=seasons)


def _scenario_config(config: Config) -> Config:
    seasons = SeasonsConfig(
        timezone="America/Sao_Paulo",
        seasons=[Season(label="t", starts_at=date(2026, 9, 1), ends_at=date(2026, 9, 30))],
    )
    best_n = config.ranking.best_n.model_copy(update={"fraction": 0.5})
    ranking = config.ranking.model_copy(update={"best_n": best_n})
    rules = config.rules.model_copy(update={"exclude": ["T5"]})
    return dataclasses.replace(config, seasons=seasons, ranking=ranking, rules=rules)


def _scenario_tournaments() -> tuple[ArchivedTournament, ...]:
    return (
        _tournament(
            "T1",
            6,
            [
                ("A", 1, 10),
                ("D", 2, 8),
                ("F", 3, 6),
                ("G", 4, 5),
                ("B", 5, 4),
                ("C", 6, 3),
                ("H", 7, 2),
                ("I", 8, 2),
            ],
        ),
        _tournament("T2", 13, [("A", 1, 8), ("B", 2, 5), ("G", 3, 4), ("F", 4, 3), ("D", 5, 1)]),
        _tournament("T3", 20, [("A", 1, 6), ("G", 2, 1)]),
        _tournament("T4", 27, [("A", 1, 1)]),
        _tournament("T5", 28, [("Excluido", 1, 99)]),
        _tournament("TOUT", 31, [("Zed", 1, 50)], month=8),
    )


def _scope_config(config: Config) -> Config:
    seasons = SeasonsConfig(
        timezone="America/Sao_Paulo",
        seasons=[Season(label="h2", starts_at=date(2026, 7, 1), ends_at=date(2026, 12, 31))],
    )
    return dataclasses.replace(config, seasons=seasons)


def _scope_tournaments() -> tuple[ArchivedTournament, ...]:
    return (
        _tournament("TJ", 5, [("A", 1, 10), ("B", 2, 5)], month=7),
        _tournament("TS1", 6, [("A", 1, 8), ("C", 2, 4)]),
        _tournament("TS2", 13, [("A", 1, 6), ("B", 2, 3)]),
        _tournament("TS3", 20, [("A", 1, 4), ("C", 2, 2)]),
        _tournament("TO", 4, [("A", 1, 2), ("B", 2, 1)], month=10),
    )


def _tournament(
    arena_id: str,
    day: int,
    standings: list[tuple[str, int, int]],
    *,
    month: int = 9,
) -> ArchivedTournament:
    starts_at = datetime(2026, month, day, 22, 0, tzinfo=timezone.utc)
    return ArchivedTournament(
        id=arena_id,
        name=arena_id,
        edition=1,
        starts_at=starts_at,
        finishes_at=starts_at + timedelta(hours=1),
        minutes=60,
        clock_initial=300,
        clock_increment=2,
        perf="blitz",
        variant="standard",
        rated=True,
        created_by="organizador",
        team_member="cavaleiros-do-centro",
        nb_players=len(standings),
        games=1,
        checks=(),
        override=None,
        fetched_at=starts_at,
        standings=tuple(_standing(username, rank, score) for username, rank, score in standings),
    )


def _standing(username: str, rank: int, score: int) -> ArchivedStanding:
    return ArchivedStanding(
        username=username,
        rank=rank,
        score=score,
        rating=1500,
        performance=1500,
        games=1,
        title=None,
        sheet="",
    )
