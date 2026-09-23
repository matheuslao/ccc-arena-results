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
from ccc_arena_results.config import (
    AliasesConfig,
    Config,
    Person,
    Season,
    SeasonsConfig,
    load,
)
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


def test_site_gera_paginas_de_torneios_e_jogadores(tmp_path, config, client) -> None:
    tournaments = _collected(tmp_path, config, client)
    output = tmp_path / "site"

    build_site(config, tournaments, output, now=NOW)

    assert (output / "torneios.html").is_file()
    assert (output / "torneios.json").is_file()
    assert (output / "jogadores.json").is_file()
    assert (output / "torneio" / "BvMsByPD.html").is_file()
    assert (output / "jogador" / "kleberbios.html").is_file()


def test_pagina_de_torneios_lista_com_vencedor(tmp_path, config, client) -> None:
    tournaments = _collected(tmp_path, config, client)
    output = tmp_path / "site"

    build_site(config, tournaments, output, now=NOW)

    html = (output / "torneios.html").read_text(encoding="utf-8")
    assert "Arena dos Cavaleiros 16a ed. Arena" in html
    assert 'href="torneio/BvMsByPD.html"' in html
    assert 'href="jogador/kleberbios.html"' in html
    assert "12" in html  # número de jogadores

    payload = json.loads((output / "torneios.json").read_text(encoding="utf-8"))
    assert payload["tournaments"][0]["id"] == "BvMsByPD"
    assert payload["tournaments"][0]["winner"] == {
        "username": "kleberbios",
        "person": "kleberbios",
    }


def test_pagina_de_torneio_mostra_classificacao(tmp_path, config, client) -> None:
    tournaments = _collected(tmp_path, config, client)
    output = tmp_path / "site"

    build_site(config, tournaments, output, now=NOW)

    html = (output / "torneio" / "BvMsByPD.html").read_text(encoding="utf-8")
    assert "Classificação final" in html
    assert "kleberbios" in html
    assert "Performance" in html
    assert 'href="../jogador/kleberbios.html"' in html


def test_pagina_de_jogador_mostra_resultados(tmp_path, config, client) -> None:
    tournaments = _collected(tmp_path, config, client)
    output = tmp_path / "site"

    build_site(config, tournaments, output, now=NOW)

    html = (output / "jogador" / "kleberbios.html").read_text(encoding="utf-8")
    assert "Resultados" in html
    assert 'href="../torneio/BvMsByPD.html"' in html
    assert ">19<" in html

    payload = json.loads((output / "jogadores.json").read_text(encoding="utf-8"))
    leader = next(p for p in payload["players"] if p["person"] == "kleberbios")
    assert leader["usernames"] == ["kleberbios"]
    assert leader["results"][0]["rank"] == 1
    assert leader["results"][0]["score"] == 19


def test_navegacao_entre_paginas(tmp_path, config, client) -> None:
    tournaments = _collected(tmp_path, config, client)
    output = tmp_path / "site"

    build_site(config, tournaments, output, now=NOW)

    ranking = (output / "index.html").read_text(encoding="utf-8")
    listing = (output / "torneios.html").read_text(encoding="utf-8")
    tournament = (output / "torneio" / "BvMsByPD.html").read_text(encoding="utf-8")
    player = (output / "jogador" / "kleberbios.html").read_text(encoding="utf-8")

    assert 'href="torneios.html"' in ranking
    assert 'href="jogador/kleberbios.html"' in ranking
    assert 'href="torneio/BvMsByPD.html"' in listing
    assert 'href="../index.html"' in tournament
    assert 'href="../torneios.html"' in tournament
    assert 'href="../jogador/kleberbios.html"' in tournament
    assert 'href="../torneio/BvMsByPD.html"' in player


def test_jogador_com_alias_aparece_consolidado(config, tmp_path) -> None:
    scenario = _scenario(config, aliases=[("Fulano", ["antigo", "novo"])])
    tournaments = (
        _tournament("T1", 6, [("antigo", 1, 10), ("B", 2, 6)]),
        _tournament("T2", 13, [("novo", 1, 8), ("B", 2, 5)]),
    )
    output = tmp_path / "site"

    build_site(scenario, tournaments, output, now=NOW)

    page = (output / "jogador" / "fulano.html").read_text(encoding="utf-8")
    assert "Fulano" in page
    assert "antigo" in page and "novo" in page
    assert 'href="../torneio/T1.html"' in page
    assert 'href="../torneio/T2.html"' in page

    listing = (output / "torneios.html").read_text(encoding="utf-8")
    assert listing.count('href="jogador/fulano.html"') == 2


def test_site_publica_recortes_de_mes_e_semestre(config, tmp_path) -> None:
    output = tmp_path / "site"

    build_site(_wide_scenario(config), _recorte_tournaments(), output, now=NOW)

    assert (output / "recorte" / "2026-09.html").is_file()
    assert (output / "recorte" / "2026-09.json").is_file()
    assert (output / "recorte" / "2026-10.html").is_file()
    assert (output / "recorte" / "2026-H2.html").is_file()
    assert (output / "recorte" / "2026-H2.json").is_file()


def test_recorte_tem_n_e_janela_proprios(config, tmp_path) -> None:
    output = tmp_path / "site"

    build_site(_wide_scenario(config), _recorte_tournaments(), output, now=NOW)

    september = json.loads((output / "recorte" / "2026-09.json").read_text(encoding="utf-8"))
    october = json.loads((output / "recorte" / "2026-10.json").read_text(encoding="utf-8"))
    semester = json.loads((output / "recorte" / "2026-H2.json").read_text(encoding="utf-8"))

    assert september["scope"] == {"kind": "month", "value": "2026-09"}
    assert (september["tournamentsConsidered"], september["bestN"]) == (3, 3)
    assert (october["tournamentsConsidered"], october["bestN"]) == (1, 1)
    assert semester["scope"] == {"kind": "semester", "value": "2026-H2"}
    assert (semester["tournamentsConsidered"], semester["bestN"]) == (4, 3)


def test_recorte_com_menos_de_tres_sem_podio(config, tmp_path) -> None:
    output = tmp_path / "site"

    build_site(_wide_scenario(config), _recorte_tournaments(), output, now=NOW)

    september = (output / "recorte" / "2026-09.html").read_text(encoding="utf-8")
    october = (output / "recorte" / "2026-10.html").read_text(encoding="utf-8")

    assert "Pódio" in september
    assert "Campeão" in september
    assert "Descartados" in september

    assert "Sem campeão eleito" in october
    assert "Pódio" not in october


def test_navegacao_entre_temporada_e_recortes(config, tmp_path) -> None:
    output = tmp_path / "site"

    build_site(_wide_scenario(config), _recorte_tournaments(), output, now=NOW)

    season = (output / "index.html").read_text(encoding="utf-8")
    recorte = (output / "recorte" / "2026-09.html").read_text(encoding="utf-8")

    assert 'href="recorte/2026-09.html"' in season
    assert 'href="recorte/2026-H2.html"' in season
    assert "Mês 2026-09" in season
    assert 'href="../index.html"' in recorte
    assert 'href="../torneios.html"' in recorte


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


def _scenario(config: Config, aliases: list[tuple[str, list[str]]] | None = None) -> Config:
    seasons = SeasonsConfig(
        timezone="America/Sao_Paulo",
        seasons=[Season(label="2026", starts_at=date(2026, 9, 1), ends_at=date(2026, 9, 30))],
    )
    scenario = dataclasses.replace(config, seasons=seasons)
    if aliases is not None:
        scenario = dataclasses.replace(
            scenario,
            aliases=AliasesConfig(
                people=[
                    Person(person=person, usernames=usernames)
                    for person, usernames in aliases
                ]
            ),
        )
    return scenario


def _tournaments() -> tuple[ArchivedTournament, ...]:
    return (
        _tournament("T1", 6, [("A", 1, 10), ("B", 2, 6), ("C", 3, 4)]),
        _tournament("T2", 13, [("A", 1, 8), ("B", 2, 5), ("C", 3, 3)]),
        _tournament("T3", 20, [("A", 1, 6), ("B", 2, 4), ("C", 3, 2)]),
    )


def _wide_scenario(config: Config) -> Config:
    seasons = SeasonsConfig(
        timezone="America/Sao_Paulo",
        seasons=[Season(label="2026", starts_at=date(2026, 9, 1), ends_at=date(2026, 12, 31))],
    )
    return dataclasses.replace(config, seasons=seasons)


def _recorte_tournaments() -> tuple[ArchivedTournament, ...]:
    return (
        _tournament("T1", 6, [("A", 1, 10), ("B", 2, 6)]),
        _tournament("T2", 13, [("A", 1, 8), ("B", 2, 5)]),
        _tournament("T3", 20, [("A", 1, 6), ("B", 2, 4)]),
        _tournament("T4", 4, [("A", 1, 9), ("B", 2, 3)], month=10),
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
