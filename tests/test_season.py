"""Testes das janelas de Temporada e de Recorte no fuso de referência."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from ccc_arena_results.config import Config, Season, load
from ccc_arena_results.season import (
    local_date,
    month_scope,
    scope_for,
    season_of,
    semester_scope,
)

SHIPPED = Path(__file__).resolve().parents[1] / "config"
SEASONS = load(SHIPPED).seasons


@pytest.fixture
def config() -> Config:
    return load(SHIPPED)


def _season() -> Season:
    return SEASONS.seasons[0]


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


def test_mes_e_recortado_pela_temporada() -> None:
    scope = month_scope(_season(), "2026-09")

    assert scope.kind == "month"
    assert scope.value == "2026-09"
    assert scope.starts_at.isoformat() == "2026-09-20"
    assert scope.ends_at.isoformat() == "2026-09-30"


def test_semestre_e_recortado_pela_temporada() -> None:
    scope = semester_scope(_season(), "2026-H2")

    assert scope.starts_at.isoformat() == "2026-09-20"
    assert scope.ends_at.isoformat() == "2026-12-31"


def test_recorte_fora_da_temporada_e_erro() -> None:
    with pytest.raises(ValueError):
        month_scope(_season(), "2026-08")


def test_recorte_invalido_e_erro() -> None:
    with pytest.raises(ValueError):
        month_scope(_season(), "2026-13")
    with pytest.raises(ValueError):
        semester_scope(_season(), "2026-H3")


def test_semestre_atravessa_a_virada_de_ano() -> None:
    season = Season(label="x", starts_at=date(2026, 12, 1), ends_at=date(2027, 2, 28))

    scope = semester_scope(season, "2027-H1")

    assert scope.starts_at.isoformat() == "2027-01-01"
    assert scope.ends_at.isoformat() == "2027-02-28"


def test_scope_for_escolhe_a_janela(config) -> None:
    assert scope_for(config).kind == "season"
    assert scope_for(config, month="2026-09").kind == "month"
    assert scope_for(config, semester="2026-H2").value == "2026-H2"


def test_scope_for_recusa_mes_e_semestre_juntos(config) -> None:
    with pytest.raises(ValueError):
        scope_for(config, month="2026-09", semester="2026-H2")
