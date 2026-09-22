"""Testes do arquivamento e do relatório de pendências — sem rede."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

import ccc_arena_results.cli as cli
from ccc_arena_results.archive import read_report, read_tournaments
from ccc_arena_results.config import load
from ccc_arena_results.ingest import EditionEntry, assign_editions, collect
from ccc_arena_results.rules import CHECK_ORDER
from lichess_fixtures import FIXTURES, FixtureLichess

SHIPPED = Path(__file__).resolve().parents[1] / "config"
NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
INVALID_IDS = {"KRHH63Yz", "6ehIpwWG", "KPfmJoD9"}


@pytest.fixture
def config():
    return load(SHIPPED)


@pytest.fixture
def client() -> FixtureLichess:
    return FixtureLichess(FIXTURES)


def test_arquiva_os_validos_com_classificacao_e_pgn(tmp_path, config, client) -> None:
    result = collect(config, client, tmp_path, now=NOW)

    assert len(result.archived) == 11
    tournaments = read_tournaments(tmp_path)
    assert set(tournaments) == set(result.archived)

    tournament = tournaments["BvMsByPD"]
    assert tournament.name == "Arena dos Cavaleiros 16a ed. Arena"
    assert tournament.edition == 16
    assert tournament.starts_at.isoformat() == "2026-09-20T22:00:00+00:00"
    assert tournament.finishes_at.isoformat() == "2026-09-20T23:00:00+00:00"
    assert tournament.minutes == 60
    assert tournament.nb_players == 12
    assert tournament.games == 26
    assert tournament.checks == CHECK_ORDER
    assert tournament.override is None

    leader = tournament.standings[0]
    assert leader.username == "kleberbios"
    assert leader.rank == 1
    assert leader.score == 19
    assert leader.games == 6
    assert leader.sheet == "555220"

    pgn = (tmp_path / "pgn" / "BvMsByPD.pgn").read_text(encoding="utf-8")
    assert pgn.startswith('[Event "Arena dos Cavaleiros 16a ed. Arena"]')


def test_edicao_e_atribuida_por_data(tmp_path, config, client) -> None:
    collect(config, client, tmp_path, now=NOW)

    tournaments = read_tournaments(tmp_path)
    assert tournaments["gJhPbAJk"].edition == 6
    assert tournaments["WzzKIPLX"].edition == 14
    assert tournaments["LeGVkx0x"].edition == 15
    assert tournaments["BvMsByPD"].edition == 16


def test_rodar_duas_vezes_nao_altera_nada(tmp_path, config, client) -> None:
    first = collect(config, client, tmp_path, now=NOW)
    assert first.archived
    snapshot = _snapshot(tmp_path)

    second = collect(config, client, tmp_path, now=NOW)

    assert second.archived == ()
    assert set(second.skipped) == set(first.archived)
    assert _snapshot(tmp_path) == snapshot


def test_pendencias_reportam_near_miss_e_fora_de_temporada(tmp_path, config, client) -> None:
    collect(config, client, tmp_path, now=NOW)

    report = read_report(tmp_path)
    by_kind: dict[str, list[str]] = {}
    for entry in report["entries"]:
        by_kind.setdefault(entry["kind"], []).append(entry["tournamentId"])

    assert sorted(by_kind["near-miss"]) == sorted(INVALID_IDS)
    assert len(by_kind["outside-season"]) == 10
    assert "BvMsByPD" not in by_kind["outside-season"]
    assert "edition-anomaly" not in by_kind

    near_miss = next(e for e in report["entries"] if e["tournamentId"] == "KPfmJoD9")
    assert near_miss["failedChecks"] == ["name", "team"]
    assert "restrita ao time" in near_miss["detail"]


def test_relatorio_sai_vazio_quando_nao_ha_o_que_reportar(tmp_path, config) -> None:
    fixtures = _trimmed_fixtures(tmp_path / "fixtures")
    archive = tmp_path / "archive"

    collect(config, FixtureLichess(fixtures), archive, now=NOW)

    assert read_report(archive)["entries"] == []


def test_edicao_registra_colisao_e_regressao() -> None:
    pattern = load(SHIPPED).rules.edition_pattern
    entries = [
        EditionEntry("a", _utc("2026-01-01T22:00:00Z"), "Arena dos Cavaleiros 16a ed.", None),
        EditionEntry("b", _utc("2026-01-08T22:00:00Z"), "Arena dos Cavaleiros 16a ed.", None),
        EditionEntry("c", _utc("2026-01-15T22:00:00Z"), "Arena dos Cavaleiros 15a ed.", None),
        EditionEntry("d", _utc("2026-01-22T22:00:00Z"), "Sem número no nome", None),
    ]

    editions, anomalies = assign_editions(entries, pattern)

    assert editions == {"a": 16, "b": 16, "c": 15, "d": 16}
    details = [str(anomaly["detail"]) for anomaly in anomalies]
    assert any("colide" in detail for detail in details)
    assert any("regride" in detail for detail in details)


def test_cli_collect(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "HttpLichess", lambda: FixtureLichess(FIXTURES))
    archive = tmp_path / "archive"

    code = cli.main(
        ["collect", "--config-dir", str(SHIPPED), "--archive-dir", str(archive)]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "11 novo(s)" in out
    assert (archive / "tournaments" / "BvMsByPD.json").is_file()
    assert (archive / "pendencias.json").is_file()


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _trimmed_fixtures(root: Path) -> Path:
    shutil.copytree(FIXTURES, root)
    _keep_only(root / "team_cavaleiros-do-centro.ndjson", {"BvMsByPD"})
    _keep_only(root / "created_matheuslao.ndjson", {"BvMsByPD"})
    (root / "created_vifranca.ndjson").write_text("", encoding="utf-8")
    return root


def _keep_only(path: Path, ids: set[str]) -> None:
    kept = [line for line in path.read_text(encoding="utf-8").splitlines() if json.loads(line)["id"] in ids]
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))
