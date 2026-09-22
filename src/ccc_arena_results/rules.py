"""Decisão pura: este torneio é um Torneio Válido?

Não faz rede, não lê disco. Recebe um :class:`~ccc_arena_results.lichess.Arena`
já normalizado e a configuração, e devolve o veredito com as checagens que
passaram e as que falharam. Nenhuma checagem interrompe as outras: o
organizador enxerga, de uma vez, tudo o que fez o candidato não casar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import RulesConfig
from .lichess import Arena

__all__ = ["CHECK_ORDER", "Verdict", "classify"]

CHECK_ORDER = (
    "system",
    "name",
    "variant",
    "team",
    "minutes",
    "finished",
    "players",
    "games",
)


@dataclass(frozen=True)
class Verdict:
    """O resultado da classificação, com a evidência de cada checagem."""

    passed: tuple[str, ...]
    failed: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.failed


def classify(arena: Arena, rules: RulesConfig) -> Verdict:
    """Aplica todas as checagens da regra de Torneio Válido, sem atalhos."""
    results = [
        ("system", arena.system == "arena"),
        ("name", re.search(rules.name_pattern, arena.full_name) is not None),
        ("variant", arena.variant in rules.allowed_variants),
        ("team", not rules.require_members_only or arena.team_member == rules.team),
        ("minutes", arena.minutes == rules.minutes),
        ("finished", arena.is_finished),
        ("players", arena.nb_players >= rules.min_players),
        ("games", arena.games >= rules.min_games),
    ]
    passed = tuple(name for name, ok in results if ok)
    failed = tuple(name for name, ok in results if not ok)
    return Verdict(passed=passed, failed=failed)
