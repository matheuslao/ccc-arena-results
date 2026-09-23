"""Testes da descoberta e classificação de candidatos — sem rede."""

from __future__ import annotations

from pathlib import Path

import pytest

import ccc_arena_results.cli as cli
from ccc_arena_results.config import load
from ccc_arena_results.ingest import discover
from ccc_arena_results.rules import INCLUDE
from lichess_fixtures import FIXTURES, FixtureLichess

SHIPPED = Path(__file__).resolve().parents[1] / "config"


@pytest.fixture
def config():
    return load(SHIPPED)


@pytest.fixture
def client() -> FixtureLichess:
    return FixtureLichess(FIXTURES)


def test_descobre_as_duas_fontes_e_classifica(config, client) -> None:
    candidates = discover(config, client)

    assert len(candidates) == 14
    assert all(candidate.verdict.valid for candidate in candidates)

    # Os três torneios fora do padrão entram por ``include``, com a falha registrada.
    included = {
        candidate.arena.id: candidate.verdict
        for candidate in candidates
        if candidate.verdict.override == INCLUDE
    }
    assert set(included) == {"KRHH63Yz", "KPfmJoD9", "6ehIpwWG"}
    assert included["KRHH63Yz"].failed == ("name",)
    assert included["KPfmJoD9"].failed == ("name", "team")
    assert included["6ehIpwWG"].failed == ("name", "team")


def test_ordenacao_deterministica_por_data(config, client) -> None:
    candidates = discover(config, client)

    starts = [candidate.arena.starts_at for candidate in candidates]
    assert starts == sorted(starts)
    assert candidates[0].arena.id == "KRHH63Yz"
    assert candidates[-1].arena.id == "BvMsByPD"


def test_fontes_sao_registradas(config, client) -> None:
    sources = {candidate.arena.id: candidate.sources for candidate in discover(config, client)}

    assert sources["BvMsByPD"] == ("team:cavaleiros-do-centro", "creator:matheuslao")
    assert sources["6ehIpwWG"] == ("creator:vifranca",)


def test_cli_descobre_sem_tocar_a_rede(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "HttpLichess", lambda: FixtureLichess(FIXTURES))

    code = cli.main(["discover", "--config-dir", str(SHIPPED)])
    out = capsys.readouterr().out

    assert code == 0
    assert "14 candidatos (14 válidos, 0 inválidos)" in out
    assert "KPfmJoD9" in out
    assert "incluído manualmente" in out
