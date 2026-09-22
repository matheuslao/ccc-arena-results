"""Testes da classificação de Torneio Válido — pura, sem rede.

As fixtures vêm da API real. As bordas que o histórico não tem (zero partidas,
menos de dois jogadores) são derivadas de um Arena real, não inventadas à mão.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from ccc_arena_results.config import load
from ccc_arena_results.lichess import Arena
from ccc_arena_results.rules import CHECK_ORDER, classify
from lichess_fixtures import FIXTURES

SHIPPED = Path(__file__).resolve().parents[1] / "config"
RULES = load(SHIPPED).rules


def _arena(arena_id: str) -> Arena:
    path = FIXTURES / f"arena_{arena_id}.json"
    return Arena.from_detail(json.loads(path.read_text(encoding="utf-8")))


def test_torneio_valido_passa_em_todas_as_checagens() -> None:
    verdict = classify(_arena("BvMsByPD"), RULES)

    assert verdict.valid
    assert verdict.passed == CHECK_ORDER
    assert verdict.failed == ()


def test_nome_fora_do_padrao_falha_apenas_a_checagem_de_nome() -> None:
    assert classify(_arena("KRHH63Yz"), RULES).failed == ("name",)


def test_arena_aberta_falha_nas_checagens_de_nome_e_time() -> None:
    assert classify(_arena("KPfmJoD9"), RULES).failed == ("name", "team")


def test_arena_aberta_com_time_opcional() -> None:
    rules = RULES.model_copy(update={"require_members_only": False})

    assert classify(_arena("KPfmJoD9"), rules).failed == ("name",)


@pytest.mark.parametrize(
    "change, check",
    [
        ({"system": "swiss"}, "system"),
        ({"minutes": 30}, "minutes"),
        ({"variant": "chess960"}, "variant"),
        ({"is_finished": False}, "finished"),
        ({"nb_players": 1}, "players"),
        ({"games": 0}, "games"),
    ],
)
def test_bordas_derivadas_de_uma_fixture_real(change: dict, check: str) -> None:
    arena = dataclasses.replace(_arena("BvMsByPD"), **change)

    verdict = classify(arena, RULES)

    assert not verdict.valid
    assert verdict.failed == (check,)
