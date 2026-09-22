"""Testes das correções manuais de escopo: include, exclude e atualização."""

from __future__ import annotations

import dataclasses
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import ccc_arena_results.cli as cli
from ccc_arena_results.archive import read_tournaments
from ccc_arena_results.config import Config, load
from ccc_arena_results.ingest import collect, refresh, refresh_all
from ccc_arena_results.rules import CHECK_ORDER, INCLUDE, EXCLUDE, classify
from lichess_fixtures import FIXTURES, FixtureLichess

SHIPPED = Path(__file__).resolve().parents[1] / "config"
NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def config() -> Config:
    return load(SHIPPED)


@pytest.fixture
def client() -> FixtureLichess:
    return FixtureLichess(FIXTURES)


def _with_overrides(config: Config, *, include: list[str] | None = None, exclude: list[str] | None = None) -> Config:
    rules = config.rules.model_copy(
        update={"include": include or [], "exclude": exclude or []}
    )
    return dataclasses.replace(config, rules=rules)


def test_exclude_tira_um_torneio_que_casaria_com_as_regras(config, client) -> None:
    rules = _with_overrides(config, exclude=["BvMsByPD"]).rules

    verdict = classify(client.arena("BvMsByPD"), rules)

    assert verdict.override == EXCLUDE
    assert not verdict.valid
    assert verdict.failed == ()


def test_include_traz_um_torneio_que_falharia_uma_checagem(config, client) -> None:
    rules = _with_overrides(config, include=["KRHH63Yz"]).rules

    verdict = classify(client.arena("KRHH63Yz"), rules)

    assert verdict.override == INCLUDE
    assert verdict.valid
    assert verdict.failed == ("name",)


def test_collect_nao_arquiva_um_torneio_excluido(tmp_path, config, client) -> None:
    collect(_with_overrides(config, exclude=["BvMsByPD"]), client, tmp_path, now=NOW)

    assert "BvMsByPD" not in read_tournaments(tmp_path)


def test_collect_arquiva_um_torneio_incluido_marcando_o_override(tmp_path, config, client) -> None:
    collect(_with_overrides(config, include=["KRHH63Yz"]), client, tmp_path, now=NOW)

    tournament = read_tournaments(tmp_path)["KRHH63Yz"]
    assert tournament.override == INCLUDE
    assert "name" not in tournament.checks
    assert tournament.checks == tuple(c for c in CHECK_ORDER if c != "name")


def test_refresh_atualiza_o_arquivo_e_preserva_a_edicao(tmp_path, config, client) -> None:
    collect(config, client, tmp_path, now=NOW)
    path = tmp_path / "tournaments" / "BvMsByPD.json"
    before = path.read_bytes()

    result = refresh(config, client, tmp_path, "BvMsByPD", now=NOW + timedelta(hours=1))

    assert result.updated == ("BvMsByPD",)
    assert path.read_bytes() != before
    tournament = read_tournaments(tmp_path)["BvMsByPD"]
    assert tournament.fetched_at == NOW + timedelta(hours=1)
    assert tournament.edition == 16


def test_refresh_de_torneio_nao_arquivado_e_sinalizado(tmp_path, config, client) -> None:
    result = refresh(config, client, tmp_path, "BvMsByPD", now=NOW)

    assert result.missing == ("BvMsByPD",)


def test_refresh_tira_do_arquivo_um_torneio_excluido(tmp_path, config, client) -> None:
    collect(config, client, tmp_path, now=NOW)

    result = refresh(
        _with_overrides(config, exclude=["BvMsByPD"]), client, tmp_path, "BvMsByPD", now=NOW
    )

    assert result.removed == ("BvMsByPD",)
    assert not (tmp_path / "tournaments" / "BvMsByPD.json").exists()
    assert not (tmp_path / "pgn" / "BvMsByPD.pgn").exists()


def test_refresh_all_reprocessa_todos_os_arquivados(tmp_path, config, client) -> None:
    collect(config, client, tmp_path, now=NOW)
    later = NOW + timedelta(hours=1)

    result = refresh_all(config, client, tmp_path, now=later)

    assert len(result.updated) == 11
    assert result.removed == ()
    tournaments = read_tournaments(tmp_path)
    assert all(tournament.fetched_at == later for tournament in tournaments.values())


def test_cli_refresh(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "HttpLichess", lambda: FixtureLichess(FIXTURES))
    archive = tmp_path / "archive"
    cli.main(["collect", "--config-dir", str(SHIPPED), "--archive-dir", str(archive)])
    capsys.readouterr()

    code = cli.main(
        ["refresh", "BvMsByPD", "--config-dir", str(SHIPPED), "--archive-dir", str(archive)]
    )

    assert code == 0
    assert "Atualizado: BvMsByPD" in capsys.readouterr().out


def test_cli_refresh_de_id_desconhecido(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "HttpLichess", lambda: FixtureLichess(FIXTURES))

    code = cli.main(
        ["refresh", "ZZZZ", "--config-dir", str(SHIPPED), "--archive-dir", str(tmp_path)]
    )

    assert code == 1
    assert "não arquivado" in capsys.readouterr().err


def test_cli_discover_marca_override(tmp_path, monkeypatch, capsys) -> None:
    directory = _config_dir(tmp_path, include=["KRHH63Yz"], exclude=["BvMsByPD"])
    monkeypatch.setattr(cli, "HttpLichess", lambda: FixtureLichess(FIXTURES))

    code = cli.main(["discover", "--config-dir", str(directory)])
    out = capsys.readouterr().out

    assert code == 0
    assert "incluído manualmente" in out
    assert "excluído manualmente" in out


def _config_dir(tmp_path: Path, **rules_updates: list[str]) -> Path:
    directory = tmp_path / "config"
    shutil.copytree(SHIPPED, directory)
    path = directory / "rules.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(rules_updates)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return directory
