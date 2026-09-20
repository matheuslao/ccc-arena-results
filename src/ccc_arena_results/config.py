"""Configuração do projeto: carregamento e validação.

Quatro arquivos, separados por cadência de mudança:

- ``seasons.json`` — a Temporada e o fuso de referência.
- ``rules.json`` — o que faz de um torneio um Torneio Válido.
- ``ranking.json`` — como o Ranking agrega os Resultados.
- ``aliases.json`` — quem é quem (trocas de nick).

A validação nunca para no primeiro erro: ela acumula todos os problemas e
reporta cada um apontando o arquivo e o campo, para o organizador corrigir
tudo de uma vez.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

__all__ = [
    "FILES",
    "TIE_BREAKS",
    "AliasesConfig",
    "Config",
    "ConfigError",
    "RankingConfig",
    "RulesConfig",
    "SeasonsConfig",
    "check",
    "load",
]

FILES = ("seasons.json", "rules.json", "ranking.json", "aliases.json")

TIE_BREAKS = ("firstPlaces", "bestSingleScore", "tournamentsPlayed")


class ConfigError(Exception):
    """Configuração inválida. Carrega a lista de problemas encontrados."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = list(problems)
        super().__init__("\n".join(self.problems))


class _Model(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class Season(_Model):
    label: str = Field(min_length=1)
    starts_at: date = Field(alias="startsAt")
    ends_at: date = Field(alias="endsAt")

    @model_validator(mode="after")
    def _ordered(self) -> Season:
        if self.starts_at >= self.ends_at:
            raise ValueError("startsAt deve ser anterior a endsAt")
        return self


class SeasonsConfig(_Model):
    timezone: str
    seasons: list[Season] = Field(min_length=1)

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"fuso desconhecido: {value!r}") from exc
        return value

    @field_validator("seasons")
    @classmethod
    def _unique_labels(cls, value: list[Season]) -> list[Season]:
        labels = [season.label for season in value]
        repeated = sorted({label for label in labels if labels.count(label) > 1})
        if repeated:
            raise ValueError(f"temporadas com rótulo repetido: {repeated}")
        return value


class RulesConfig(_Model):
    team: str = Field(min_length=1)
    name_pattern: str = Field(alias="namePattern", min_length=1)
    edition_pattern: str = Field(alias="editionPattern", min_length=1)
    minutes: int = Field(gt=0)
    require_members_only: bool = Field(alias="requireMembersOnly")
    allowed_variants: list[str] = Field(alias="allowedVariants", min_length=1)
    min_players: int = Field(alias="minPlayers", ge=1)
    min_games: int = Field(alias="minGames", ge=1)
    scan_creators: list[str] = Field(alias="scanCreators")
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)

    @field_validator("name_pattern", "edition_pattern")
    @classmethod
    def _compilable(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"expressão regular inválida: {exc}") from exc
        return value

    @field_validator("edition_pattern")
    @classmethod
    def _captures_edition(cls, value: str) -> str:
        if re.compile(value).groups < 1:
            raise ValueError("deve conter um grupo de captura com o número da edição")
        return value

    @model_validator(mode="after")
    def _overrides_disjoint(self) -> RulesConfig:
        both = sorted(set(self.include) & set(self.exclude))
        if both:
            raise ValueError(f"ids em include e exclude ao mesmo tempo: {both}")
        return self


class BestN(_Model):
    fraction: float = Field(gt=0, le=1)
    rounding: Literal["ceil", "floor", "round"] = "ceil"


class Eligibility(_Model):
    min_participation_fraction: float = Field(
        alias="minParticipationFraction", ge=0, le=1
    )


class RankingConfig(_Model):
    best_n: BestN = Field(alias="bestN")
    eligibility: Eligibility
    min_tournaments_for_champion: int = Field(
        alias="minTournamentsForChampion", ge=1
    )
    tie_break: list[str] = Field(alias="tieBreak", min_length=1)

    @field_validator("tie_break")
    @classmethod
    def _known_tie_breaks(cls, value: list[str]) -> list[str]:
        unknown = [item for item in value if item not in TIE_BREAKS]
        if unknown:
            raise ValueError(
                f"critérios de desempate desconhecidos: {unknown}; use {list(TIE_BREAKS)}"
            )
        if len(set(value)) != len(value):
            raise ValueError("critérios de desempate repetidos")
        return value


class Person(_Model):
    person: str = Field(min_length=1)
    usernames: list[str] = Field(min_length=1)


class AliasesConfig(_Model):
    people: list[Person] = Field(default_factory=list)

    @model_validator(mode="after")
    def _usernames_are_owned_once(self) -> AliasesConfig:
        owner: dict[str, str] = {}
        for entry in self.people:
            for username in entry.usernames:
                if username in owner:
                    raise ValueError(
                        f"username {username!r} aparece em "
                        f"{owner[username]!r} e {entry.person!r}"
                    )
                owner[username] = entry.person
        return self


@dataclass(frozen=True)
class Config:
    """A configuração já validada."""

    seasons: SeasonsConfig
    rules: RulesConfig
    ranking: RankingConfig
    aliases: AliasesConfig


_MODELS: dict[str, type[_Model]] = {
    "seasons.json": SeasonsConfig,
    "rules.json": RulesConfig,
    "ranking.json": RankingConfig,
    "aliases.json": AliasesConfig,
}


def _read(config_dir: Path) -> tuple[dict[str, Any], list[str]]:
    raw: dict[str, Any] = {}
    problems: list[str] = []
    for filename in FILES:
        path = Path(config_dir) / filename
        if not path.is_file():
            problems.append(f"{filename}: arquivo não encontrado em {path}")
            continue
        try:
            raw[filename] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"{filename}: JSON inválido: {exc}")
    return raw, problems


def _format(filename: str, error: ValidationError) -> list[str]:
    messages = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"]) or "(raiz)"
        messages.append(f"{filename}: {location}: {item['msg']}")
    return messages


def check(config_dir: Path) -> list[str]:
    """Devolve os problemas encontrados; lista vazia quando está tudo certo."""
    raw, problems = _read(config_dir)
    if problems:
        return problems
    for filename, model in _MODELS.items():
        try:
            model.model_validate(raw[filename])
        except ValidationError as exc:
            problems.extend(_format(filename, exc))
    return problems


def load(config_dir: Path) -> Config:
    """Carrega a configuração validada, ou levanta ``ConfigError``."""
    problems = check(config_dir)
    if problems:
        raise ConfigError(problems)
    raw, _ = _read(config_dir)
    return Config(
        seasons=SeasonsConfig.model_validate(raw["seasons.json"]),
        rules=RulesConfig.model_validate(raw["rules.json"]),
        ranking=RankingConfig.model_validate(raw["ranking.json"]),
        aliases=AliasesConfig.model_validate(raw["aliases.json"]),
    )
