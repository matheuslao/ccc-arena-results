"""Temporada e Recortes: janelas de calendário no fuso de referência.

O arquivo guarda instantes em UTC, mas a alocação de um Torneio numa Temporada
— e, adiante, num Recorte — é feita no fuso configurado. Sem essa âncora, um
torneio perto da meia-noite UTC cairia no período errado.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from .config import Season, SeasonsConfig

__all__ = ["local_date", "season_of"]


def local_date(instant: datetime, timezone: str) -> date:
    """A data local de um instante, no fuso de referência."""
    return instant.astimezone(ZoneInfo(timezone)).date()


def season_of(instant: datetime, seasons: SeasonsConfig) -> Season | None:
    """A Temporada que contém o instante, ou ``None`` se estiver fora de todas.

    A janela da Temporada é inclusiva nas duas pontas, no fuso de referência.
    """
    day = local_date(instant, seasons.timezone)
    for season in seasons.seasons:
        if season.starts_at <= day <= season.ends_at:
            return season
    return None
