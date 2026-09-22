"""Temporada e Recortes: janelas de calendário no fuso de referência.

O arquivo guarda instantes em UTC, mas a alocação de um Torneio numa Temporada
ou num Recorte é feita no fuso configurado. Sem essa âncora, um torneio perto da
meia-noite UTC cairia no período errado.

Um Recorte é uma janela de calendário — mês ou semestre — **intersectada com a
janela da Temporada**: setembro/2026, com a Temporada começando em 20/09, vale
de 20/09 a 30/09. Temporadas e Recortes não têm estado próprio: são sempre
recalculados.
"""

from __future__ import annotations

import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .config import Config, Season, SeasonsConfig

__all__ = [
    "Scope",
    "local_date",
    "month_scope",
    "resolve_season",
    "scope_for",
    "season_of",
    "season_scope",
    "semester_scope",
]

_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_SEMESTER = re.compile(r"^(\d{4})-H([12])$")


@dataclass(frozen=True)
class Scope:
    """A janela sobre a qual um Ranking é calculado."""

    kind: str
    value: str
    season: str
    starts_at: date
    ends_at: date


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


def resolve_season(config: Config, label: str | None) -> Season:
    """A Temporada pedida; sem rótulo, a única configurada."""
    seasons = config.seasons.seasons
    if label is None:
        if len(seasons) == 1:
            return seasons[0]
        options = ", ".join(season.label for season in seasons)
        raise ValueError(f"mais de uma Temporada configurada; use --season ({options})")
    for season in seasons:
        if season.label == label:
            return season
    raise ValueError(f"Temporada desconhecida: {label}")


def scope_for(
    config: Config,
    *,
    season_label: str | None = None,
    month: str | None = None,
    semester: str | None = None,
) -> Scope:
    """A janela pedida: a Temporada inteira, um mês ou um semestre."""
    if month is not None and semester is not None:
        raise ValueError("escolha --month ou --semester, não os dois")
    season = resolve_season(config, season_label)
    if month is not None:
        return month_scope(season, month)
    if semester is not None:
        return semester_scope(season, semester)
    return season_scope(season)


def season_scope(season: Season) -> Scope:
    """A janela inteira de uma Temporada."""
    return Scope(
        kind="season",
        value=season.label,
        season=season.label,
        starts_at=season.starts_at,
        ends_at=season.ends_at,
    )


def month_scope(season: Season, value: str) -> Scope:
    """A janela de um mês, recortada pela Temporada."""
    match = _MONTH.match(value)
    if match is None:
        raise ValueError(f"mês inválido: {value!r} (use AAAA-MM)")
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"mês inválido: {value!r}")
    starts_at, ends_at = _clip(
        date(year, month, 1), date(year, month, monthrange(year, month)[1]), season
    )
    return Scope(
        kind="month",
        value=value,
        season=season.label,
        starts_at=starts_at,
        ends_at=ends_at,
    )


def semester_scope(season: Season, value: str) -> Scope:
    """A janela de um semestre, recortada pela Temporada."""
    match = _SEMESTER.match(value)
    if match is None:
        raise ValueError(f"semestre inválido: {value!r} (use AAAA-H1 ou AAAA-H2)")
    year, half = int(match.group(1)), int(match.group(2))
    if half == 1:
        starts_at, ends_at = date(year, 1, 1), date(year, 6, 30)
    else:
        starts_at, ends_at = date(year, 7, 1), date(year, 12, 31)
    starts_at, ends_at = _clip(starts_at, ends_at, season)
    return Scope(
        kind="semester",
        value=value,
        season=season.label,
        starts_at=starts_at,
        ends_at=ends_at,
    )


def _clip(starts_at: date, ends_at: date, season: Season) -> tuple[date, date]:
    start = max(starts_at, season.starts_at)
    end = min(ends_at, season.ends_at)
    if start > end:
        raise ValueError(
            f"janela {starts_at}..{ends_at} fora da Temporada {season.label}"
        )
    return start, end
