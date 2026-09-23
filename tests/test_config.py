"""Testes do carregador e do validador de configuração."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ccc_arena_results.cli import main
from ccc_arena_results.config import ConfigError, check, load

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED = REPO_ROOT / "config"


def make_config(tmp_path: Path) -> Path:
    """Copia a configuração real para um diretório temporário."""
    directory = tmp_path / "config"
    shutil.copytree(SHIPPED, directory)
    return directory


def edit(directory: Path, filename: str, mutate: Callable[[Any], None]) -> Path:
    path = directory / filename
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return directory


def test_a_configuracao_do_repositorio_e_valida() -> None:
    assert check(SHIPPED) == []

    config = load(SHIPPED)
    season = config.seasons.seasons[0]

    assert season.label == "2026"
    assert season.starts_at.isoformat() == "2026-01-01"
    assert season.ends_at.isoformat() == "2026-12-31"
    assert config.seasons.timezone == "America/Sao_Paulo"
    assert config.rules.team == "cavaleiros-do-centro"
    assert config.rules.minutes == 60
    assert config.rules.include == ["KRHH63Yz", "KPfmJoD9", "6ehIpwWG"]
    assert config.rules.exclude == []
    assert config.ranking.best_n.fraction == 0.75
    assert config.ranking.eligibility.min_participation_fraction == 0.5
    assert config.ranking.min_tournaments_for_champion == 3
    assert config.aliases.people == []


def test_arquivo_ausente_e_reportado(tmp_path: Path) -> None:
    directory = make_config(tmp_path)
    (directory / "rules.json").unlink()

    problems = check(directory)

    assert len(problems) == 1
    assert problems[0].startswith("rules.json: arquivo não encontrado")


def test_json_invalido_e_reportado(tmp_path: Path) -> None:
    directory = make_config(tmp_path)
    (directory / "ranking.json").write_text("{ nao e json", encoding="utf-8")

    problems = check(directory)

    assert any(problem.startswith("ranking.json: JSON inválido") for problem in problems)


def test_temporada_precisa_comecar_antes_de_terminar(tmp_path: Path) -> None:
    directory = make_config(tmp_path)
    edit(
        directory,
        "seasons.json",
        lambda payload: payload["seasons"][0].update(
            startsAt="2026-12-31", endsAt="2026-09-20"
        ),
    )

    problems = check(directory)

    assert any(problem.startswith("seasons.json: seasons.0") for problem in problems)


def test_fuso_desconhecido_e_reportado(tmp_path: Path) -> None:
    directory = make_config(tmp_path)
    edit(
        directory,
        "seasons.json",
        lambda payload: payload.update(timezone="Marte/Olympus"),
    )

    problems = check(directory)

    assert any("seasons.json: timezone" in problem for problem in problems)


def test_campo_desconhecido_e_rejeitado(tmp_path: Path) -> None:
    directory = make_config(tmp_path)
    edit(directory, "rules.json", lambda payload: payload.update(minutos=60))

    problems = check(directory)

    assert any("minutos" in problem for problem in problems)


def test_fracao_fora_do_intervalo_e_reportada(tmp_path: Path) -> None:
    directory = make_config(tmp_path)
    edit(directory, "ranking.json", lambda payload: payload["bestN"].update(fraction=1.5))

    problems = check(directory)

    assert any("bestN.fraction" in problem for problem in problems)


def test_criterio_de_desempate_desconhecido_e_reportado(tmp_path: Path) -> None:
    directory = make_config(tmp_path)
    edit(
        directory,
        "ranking.json",
        lambda payload: payload.update(tieBreak=["sorte"]),
    )

    problems = check(directory)

    assert any("ranking.json: tieBreak" in problem for problem in problems)


def test_ids_nos_dois_override_e_reportado(tmp_path: Path) -> None:
    directory = make_config(tmp_path)
    edit(
        directory,
        "rules.json",
        lambda payload: payload.update(include=["abc123"], exclude=["abc123"]),
    )

    problems = check(directory)

    assert any("include e exclude" in problem for problem in problems)


def test_username_nao_pode_ser_de_duas_pessoas(tmp_path: Path) -> None:
    directory = make_config(tmp_path)
    edit(
        directory,
        "aliases.json",
        lambda payload: payload.update(
            people=[
                {"person": "Fulano", "usernames": ["fulano_velho"]},
                {"person": "Beltrano", "usernames": ["fulano_velho"]},
            ]
        ),
    )

    problems = check(directory)

    assert any("aliases.json" in problem and "fulano_velho" in problem for problem in problems)


def test_load_levanta_config_error(tmp_path: Path) -> None:
    directory = make_config(tmp_path)
    (directory / "aliases.json").unlink()

    with pytest.raises(ConfigError) as caught:
        load(directory)

    assert caught.value.problems


def test_cli_sai_zero_quando_a_configuracao_e_valida(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["config", "check", "--config-dir", str(SHIPPED)]) == 0
    assert "ok" in capsys.readouterr().out


def test_cli_aponta_o_arquivo_e_sai_diferente_de_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = make_config(tmp_path)
    (directory / "aliases.json").unlink()

    exit_code = main(["config", "check", "--config-dir", str(directory)])

    assert exit_code == 1
    assert "aliases.json" in capsys.readouterr().err
