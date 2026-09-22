"""Testes do site — HTML estático e JSON derivado, sem rede."""

from __future__ import annotations

import dataclasses
import json
import socket
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import ccc_arena_results.cli as cli
from ccc_arena_results.archive import ArchivedStanding, ArchivedTournament, read_tournaments
from ccc_arena_results.config import Config, Season, SeasonsConfig, load
from ccc_arena_results.ingest import collect
from ccc_arena_results.rank import build
from ccc_arena_results.season import scope_for
from ccc_arena_results.site import (
    INDEX_FILE,
    RANKING_FILE,
    build as build_site,
    render_ranking_page,
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


def _collected(tmp_path, config, client) -> tuple[ArchivedTournament, ...]:
    archive = tmp_path / "archive"
    collect(config, client, archive, now=NOW)
    return tuple(read_tournaments(archive).values())


def test_site_gera_html_e_json(tmp_path, config, client) -> None:
    tournaments = _collected(tmp_path, config, client)
    output = tmp_path / "site"

    build_site(config, tournaments, output, now=NOW)

    assert (output / INDEX_FILE).is_file()
    assert (output / RANKING_FILE).is_file()
    assert (output / "assets" / "style.css").is_file()

    html = (output / INDEX_FILE).read_text(encoding="utf-8")
    assert "Arena dos Cavaleiros" in html
    assert "Temporada 2026" in html

    payload = json.loads((output / RANKING_FILE).read_text(encoding="utf-8"))
    assert payload["scope"] == {"kind": "season", "value": "2026"}
    assert payload["rows"]


def test_pagina_explica_as_regras(tmp_path, config, client) -> None:
    tournaments = _collected(tmp_path, config, client)

    html = render_ranking_page(build(config, tournaments, scope_for(config), now=NOW), config)

    assert "Melhores N" in html
    assert "75%" in html
    assert "50%" in html
    assert "ao menos 3 Torneios Válidos" in html
    assert "Desempate" in html


def test_pagina_mostra_a_decomposicao(tmp_path, config, client) -> None:
    tournaments = _collected(tmp_path, config, client)

    html = render_ranking_page(build(config, tournaments, scope_for(config), now=NOW), config)

    assert "Contados" in html
    assert "Descartados" in html
    assert "BvMsByPD: 19" in html
    assert 'class="counted"' in html


def test_podio_da_temporada(config) -> None:
    scenario = _scenario(config)

    html = render_ranking_page(build(scenario, _tournaments(), scope_for(scenario), now=NOW), scenario)

    assert "Pódio" in html
    assert "Campeão" in html
    assert 'class="podium-1"' in html


def test_sem_campeao_nao_mostra_podio(tmp_path, config, client) -> None:
    tournaments = _collected(tmp_path, config, client)

    html = render_ranking_page(build(config, tournaments, scope_for(config), now=NOW), config)

    assert "Sem campeão eleito" in html
    assert "Pódio" not in html


def test_nome_de_jogador_e_escapado(config) -> None:
    scenario = _scenario(config)
    tournament = _tournament("TX", 6, [("<b>hacker</b>", 1, 5)])

    html = render_ranking_page(
        build(scenario, (tournament,), scope_for(scenario), now=NOW), scenario
    )

    assert "<b>hacker</b>" not in html
    assert "&lt;b&gt;hacker&lt;/b&gt;" in html


def test_site_nao_toca_a_rede(tmp_path, config, client, monkeypatch) -> None:
    tournaments = _collected(tmp_path, config, client)

    def _explode(*args, **kwargs):
        raise AssertionError("o site não pode tocar a rede")

    monkeypatch.setattr(socket, "socket", _explode)

    output = tmp_path / "site"
    build_site(config, tournaments, output, now=NOW)

    assert (output / INDEX_FILE).is_file()


def test_cli_site(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "HttpLichess", lambda: FixtureLichess(FIXTURES))
    archive = tmp_path / "archive"
    output = tmp_path / "site"
    cli.main(["collect", "--config-dir", str(SHIPPED), "--archive-dir", str(archive)])
    capsys.readouterr()

    code = cli.main(
        [
            "site",
            "--config-dir",
            str(SHIPPED),
            "--archive-dir",
            str(archive),
            "--output-dir",
            str(output),
        ]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "Site gerado" in out
    assert (output / INDEX_FILE).is_file()


def test_cli_site_recusa_temporada_desconhecida(tmp_path, capsys) -> None:
    code = cli.main(
        [
            "site",
            "--season",
            "9999",
            "--config-dir",
            str(SHIPPED),
            "--archive-dir",
            str(tmp_path),
            "--output-dir",
            str(tmp_path / "site"),
        ]
    )

    assert code == 1
    assert "Temporada desconhecida" in capsys.readouterr().err


def _scenario(config: Config) -> Config:
    seasons = SeasonsConfig(
        timezone="America/Sao_Paulo",
        seasons=[Season(label="2026", starts_at=date(2026, 9, 1), ends_at=date(2026, 9, 30))],
    )
    return dataclasses.replace(config, seasons=seasons)


def _tournaments() -> tuple[ArchivedTournament, ...]:
    return (
        _tournament("T1", 6, [("A", 1, 10), ("B", 2, 6), ("C", 3, 4)]),
        _tournament("T2", 13, [("A", 1, 8), ("B", 2, 5), ("C", 3, 3)]),
        _tournament("T3", 20, [("A", 1, 6), ("B", 2, 4), ("C", 3, 2)]),
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
