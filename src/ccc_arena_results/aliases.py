"""Aliases: quem é quem no Lichess.

Usernames que são a mesma pessoa — troca de nick — entram no Ranking como um
único jogador, para que trocar de nick não apague histórico nem crie um jogador
fantasma. A tabela é manual e vive em ``aliases.json``.

Resolver é uma leitura pura sobre a configuração: um alias definido depois vale
no próximo cálculo, sem recoletar nada. Sem alias, a pessoa é a própria username
e a lista de usernames tem só ela — assim o Ranking sem Aliases sai idêntico ao
de antes.
"""

from __future__ import annotations

from .config import AliasesConfig

__all__ = ["Resolver"]


class Resolver:
    """Resolve uma username do Lichess para a pessoa canônica."""

    def __init__(self, aliases: AliasesConfig) -> None:
        self._person_by_username: dict[str, str] = {}
        self._usernames_by_person: dict[str, tuple[str, ...]] = {}
        for entry in aliases.people:
            usernames = tuple(entry.usernames)
            self._usernames_by_person[entry.person] = usernames
            for username in usernames:
                self._person_by_username[username] = entry.person

    def person(self, username: str) -> str:
        """A pessoa dona da username; a própria username se não houver alias."""
        return self._person_by_username.get(username, username)

    def usernames(self, person: str) -> tuple[str, ...]:
        """Todas as usernames conhecidas da pessoa."""
        return self._usernames_by_person.get(person, (person,))
