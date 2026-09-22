"""Testes dos Aliases — usernames da mesma pessoa somam um único jogador."""

from __future__ import annotations

import dataclasses
import json
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import ccc_arena_results.cli as cli
from ccc_arena_results.aliases import Resolver
from ccc_arena_results.archive import ArchivedStanding, ArchivedTournament
from ccc_arena_results.config import (
    AliasesConfig,
    Config,
    Person,
    Season,
    SeasonsConfig,
    load,
)
from ccc_arena_results.rank import build
from ccc_arena_results.season import scope_for
from lichess_fixtures import FIXTURES, FixtureLichess

SHIPPED = Path(__file__).resolve().parents[1] / "config"
NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def config() -> Config:
    return load(SHIPPED)


def test_resolver_sem_alias_e_a_propria_username() -> None:
    resolver = Resolver(AliasesConfig())

    assert resolver.person("kleberbios") == "kleberbios"
    assert resolver.usernames("kleberbios") == ("kleberbios",)


def test_resolver_agrupa_as_usernames_da_pessoa() -> None:
    resolver = Resolver(
        AliasesConfig(people=[Person(person="Kleber", usernames=["kleberbios", "kb"])])
    )

    assert resolver.person("kb") == "Kleber"
    assert resolver.usernames("Kleber") == ("kleberbios", "kb")


def test_duas_usernames_somam_um_unico_jogador(config) -> None:
    scenario = _scenario(config, aliases=[("Fulano", ["antigo", "novo"])])

    ranking = build(scenario, _tournaments(), scope_for(scenario), now=NOW)

    assert len(ranking.rows) == 1
    row = ranking.rows[0]
    assert row.person == "Fulano"
    assert row.usernames == ("antigo", "novo")
    assert (row.total, row.counted, row.played) == (18, 2, 2)
    assert row.participation == 1.0
    assert row.eligible is True


def test_sem_aliases_cada_username_e_um_jogador(config) -> None:
    scenario = _scenario(config)

    ranking = build(scenario, _tournaments(), scope_for(scenario), now=NOW)

    totals = {row.person: row.total for row in ranking.rows}
    assert totals == {"antigo": 10, "novo": 8}
    assert all(row.usernames == (row.person,) for row in ranking.rows)


def test_alias_definido_depois_vale_ao_recalcular(config) -> None:
    tournaments = _tournaments()
    scenario = _scenario(config)

    before = build(scenario, tournaments, scope_for(scenario), now=NOW)
    assert {row.person for row in before.rows} == {"antigo", "novo"}

    # O mesmo arquivo, recalculado com a tabela de Aliases preenchida.
    with_alias = _with_aliases(scenario, [("Fulano", ["antigo", "novo"])])
    after = build(with_alias, tournaments, scope_for(with_alias), now=NOW)

    assert [row.person for row in after.rows] == ["Fulano"]
    assert after.rows[0].total == 18


def test_cli_rank_mostra_as_usernames_da_pessoa(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "HttpLichess", lambda: FixtureLichess(FIXTURES))
    archive = tmp_path / "archive"
    config_dir = _copy_config(tmp_path)
    cli.main(["collect", "--config-dir", str(config_dir), "--archive-dir", str(archive)])
    capsys.readouterr()

    _edit_aliases(config_dir, [("Kleber", ["kleberbios", "emaheu"])])

    code = cli.main(["rank", "--config-dir", str(config_dir), "--archive-dir", str(archive)])
    out = capsys.readouterr().out

    assert code == 0
    assert "Kleber (kleberbios, emaheu)" in out


def _scenario(config: Config, aliases: list[tuple[str, list[str]]] | None = None) -> Config:
    seasons = SeasonsConfig(
        timezone="America/Sao_Paulo",
        seasons=[Season(label="t", starts_at=date(2026, 9, 1), ends_at=date(2026, 9, 30))],
    )
    scenario = dataclasses.replace(config, seasons=seasons)
    if aliases is not None:
        scenario = _with_aliases(scenario, aliases)
    return scenario


def _with_aliases(config: Config, people: list[tuple[str, list[str]]]) -> Config:
    aliases = AliasesConfig(
        people=[Person(person=person, usernames=usernames) for person, usernames in people]
    )
    return dataclasses.replace(config, aliases=aliases)


def _tournaments() -> tuple[ArchivedTournament, ...]:
    return (
        _tournament("T1", 6, [("antigo", 1, 10)]),
        _tournament("T2", 13, [("novo", 1, 8)]),
    )


def _tournament(
    arena_id: str,
    day: int,
    standings: list[tuple[str, int, int]],
) -> ArchivedTournament:
    starts_at = datetime(2026, 9, day, 22, 0, tzinfo=timezone.utc)
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


def _copy_config(tmp_path: Path) -> Path:
    directory = tmp_path / "config"
    shutil.copytree(SHIPPED, directory)
    return directory


def _edit_aliases(directory: Path, people: list[tuple[str, list[str]]]) -> None:
    payload = {"people": [{"person": p, "usernames": u} for p, u in people]}
    (directory / "aliases.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
