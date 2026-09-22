"""Testes das janelas de Temporada no fuso de referência."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ccc_arena_results.config import load
from ccc_arena_results.season import local_date, season_of

SHIPPED = Path(__file__).resolve().parents[1] / "config"
SEASONS = load(SHIPPED).seasons


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def test_torneio_no_inicio_da_temporada_esta_dentro() -> None:
    assert season_of(_utc("2026-09-20T22:00:00Z"), SEASONS).label == "2026"


def test_torneio_antes_da_temporada_esta_fora() -> None:
    assert season_of(_utc("2026-09-13T22:00:00Z"), SEASONS) is None


def test_a_data_local_manda_na_borda() -> None:
    # 2026-09-20T02:00Z é 2026-09-19 23:00 em São Paulo: ainda fora do início.
    assert season_of(_utc("2026-09-20T02:00:00Z"), SEASONS) is None
    # 2026-09-20T03:00Z é 2026-09-20 00:00 em São Paulo: já dentro.
    assert season_of(_utc("2026-09-20T03:00:00Z"), SEASONS).label == "2026"


def test_depois_do_fim_da_temporada_esta_fora() -> None:
    assert season_of(_utc("2027-01-01T12:00:00Z"), SEASONS) is None


def test_data_local_no_fuso_de_referencia() -> None:
    day = local_date(_utc("2026-09-20T02:00:00Z"), "America/Sao_Paulo")

    assert day.isoformat() == "2026-09-19"
