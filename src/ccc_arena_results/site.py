"""O site: as páginas estáticas, pré-renderizadas dos dados derivados.

O site é a leitura pública do Ranking, dos Torneios e dos Jogadores. Ele recebe
os torneios já arquivados e nunca consulta o Lichess — por isso continua no ar
com a API fora. As páginas são HTML pré-renderizado, sem framework de front-end;
os dados derivados em JSON são publicados junto, para qualquer consumidor futuro
(ver ADR-0003).

O layout é um ``string.Template``; o corpo é montado por funções puras, com todo
texto vindo dos dados escapado. Gerar o site não toca a rede: a única entrada é
o arquivo canônico já coletado.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from string import Template
from typing import Any

from .aliases import Resolver
from .archive import ArchivedStanding, ArchivedTournament
from .config import AliasesConfig, Config, Season
from .rank import Ranking, RankingRow
from .rank import build as build_ranking
from .rank import in_scope
from .season import (
    Scope,
    local_date,
    month_scope,
    resolve_season,
    season_scope,
    semester_scope,
)

__all__ = [
    "Links",
    "Site",
    "build",
    "render_player_page",
    "render_ranking_page",
    "render_tournament_page",
    "render_tournaments_page",
]

INDEX_FILE = "index.html"
RANKING_FILE = "ranking.json"
TOURNAMENTS_FILE = "torneios.html"
TOURNAMENTS_JSON = "torneios.json"
PLAYERS_JSON = "jogadores.json"
STYLE_FILE = "assets/style.css"
TOURNAMENT_PAGES_DIR = "torneio"
PLAYER_PAGES_DIR = "jogador"
RECORTE_PAGES_DIR = "recorte"

_TIE_LABELS = {
    "firstPlaces": "mais primeiros lugares",
    "bestSingleScore": "melhor Resultado individual",
    "tournamentsPlayed": "mais torneios jogados",
}

_ROUNDING_LABELS = {"ceil": "cima", "floor": "baixo", "round": "o mais próximo"}

_IDENTITY = Resolver(AliasesConfig())


@dataclass(frozen=True)
class Links:
    """Como uma página referencia as outras: prefixo de caminho e slugs."""

    base: str = ""
    slugs: Mapping[str, str] = field(default_factory=dict)

    def url(self, path: str) -> str:
        return f"{self.base}{path}"

    def ranking(self) -> str:
        return self.url(INDEX_FILE)

    def tournaments(self) -> str:
        return self.url(TOURNAMENTS_FILE)

    def tournament(self, arena_id: str) -> str:
        return self.url(f"{TOURNAMENT_PAGES_DIR}/{arena_id}.html")

    def recorte(self, value: str) -> str:
        return self.url(f"{RECORTE_PAGES_DIR}/{value}.html")

    def player(self, person: str) -> str:
        slug = self.slugs.get(person) or _slug(person)
        return self.url(f"{PLAYER_PAGES_DIR}/{slug}.html")


@dataclass(frozen=True)
class Site:
    """O resultado de gerar o site: onde e o que foi escrito."""

    output_dir: Path
    ranking: Ranking
    written: tuple[Path, ...]


def build(
    config: Config,
    tournaments: tuple[ArchivedTournament, ...],
    output_dir: Path,
    *,
    season_label: str | None = None,
    now: datetime | None = None,
) -> Site:
    """Gera o site a partir dos torneios arquivados. Nunca toca a rede."""
    moment = now or datetime.now(timezone.utc)
    season = resolve_season(config, season_label)
    scope = season_scope(season)
    ranking = build_ranking(config, tournaments, scope, now=moment)
    resolver = Resolver(config.aliases)
    selected = tuple(
        sorted(
            (tournament for tournament in tournaments if in_scope(config, tournament, scope)),
            key=lambda tournament: (tournament.starts_at, tournament.id),
        )
    )
    players = _players(selected, resolver)
    slugs = _slugs(players)
    recortes = _recorte_scopes(config, season, selected)
    output_dir = Path(output_dir)

    written = [
        _write(
            output_dir / INDEX_FILE,
            render_ranking_page(ranking, config, Links("", slugs), recortes),
        ),
        _write(output_dir / RANKING_FILE, _json(ranking.to_payload())),
        _write(
            output_dir / TOURNAMENTS_FILE,
            render_tournaments_page(selected, config, Links("", slugs), resolver),
        ),
        _write(
            output_dir / TOURNAMENTS_JSON,
            _json(_tournaments_payload(selected, resolver, moment)),
        ),
        _write(
            output_dir / PLAYERS_JSON,
            _json(_players_payload(players, resolver, moment)),
        ),
    ]
    for tournament in selected:
        written.append(
            _write(
                output_dir / TOURNAMENT_PAGES_DIR / f"{tournament.id}.html",
                render_tournament_page(tournament, config, Links("../", slugs), resolver),
            )
        )
    for person, results in sorted(players.items()):
        written.append(
            _write(
                output_dir / PLAYER_PAGES_DIR / f"{slugs[person]}.html",
                render_player_page(
                    person, resolver.usernames(person), results, config, Links("../", slugs)
                ),
            )
        )
    for recorte in recortes:
        recorte_ranking = build_ranking(config, tournaments, recorte, now=moment)
        written.append(
            _write(
                output_dir / RECORTE_PAGES_DIR / f"{recorte.value}.html",
                render_ranking_page(recorte_ranking, config, Links("../", slugs)),
            )
        )
        written.append(
            _write(
                output_dir / RECORTE_PAGES_DIR / f"{recorte.value}.json",
                _json(recorte_ranking.to_payload()),
            )
        )
    written.append(_write(output_dir / STYLE_FILE, STYLE))
    return Site(output_dir=output_dir, ranking=ranking, written=tuple(written))


def render_ranking_page(
    ranking: Ranking,
    config: Config,
    links: Links = Links(),
    recortes: Sequence[Scope] = (),
) -> str:
    """O HTML da página de Ranking de uma janela."""
    body = "\n".join(
        (
            _hero(ranking),
            _rules(config, ranking),
            _podium(ranking, config),
            _table(ranking, links),
            _recortes(recortes, links),
            _footer(ranking, links),
        )
    )
    return _layout(title=_title(ranking), body=_nav(links) + "\n" + body, base=links.base)


def render_tournaments_page(
    tournaments: Sequence[ArchivedTournament],
    config: Config,
    links: Links = Links(),
    resolver: Resolver = _IDENTITY,
) -> str:
    """O HTML da lista de Torneios Válidos."""
    rows = "".join(_tournament_row(tournament, config, links, resolver) for tournament in tournaments)
    body = (
        '<header class="hero"><h1>Torneios</h1>'
        f'<p class="considered">{len(tournaments)} Torneio(s) Válido(s)</p></header>'
        "<section><table><thead><tr>"
        "<th>Data</th><th>Edição</th><th>Torneio</th><th>Jogadores</th><th>Partidas</th><th>Vencedor</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></section>"
    )
    return _layout(title="Torneios", body=_nav(links) + "\n" + body, base=links.base)


def render_tournament_page(
    tournament: ArchivedTournament,
    config: Config,
    links: Links = Links(),
    resolver: Resolver = _IDENTITY,
) -> str:
    """O HTML da página de um Torneio, com a Classificação final."""
    standings = sorted(tournament.standings, key=lambda standing: (standing.rank, standing.username))
    rows = "".join(_standing_row(standing, links, resolver) for standing in standings)
    day = local_date(tournament.starts_at, config.seasons.timezone)
    body = (
        f'<header class="hero"><h1>{escape(tournament.name)}</h1>'
        f'<p class="window">Edição {tournament.edition} — {day}</p>'
        f'<p class="considered">{tournament.nb_players} jogadores, '
        f"{tournament.games} partidas</p></header>"
        "<section><h2>Classificação final</h2><table><thead><tr>"
        "<th>#</th><th>Jogador</th><th>Score</th><th>Performance</th><th>Partidas</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></section>"
    )
    return _layout(title=tournament.name, body=_nav(links) + "\n" + body, base=links.base)


def render_player_page(
    person: str,
    usernames: Sequence[str],
    results: Sequence[tuple[ArchivedTournament, ArchivedStanding]],
    config: Config,
    links: Links = Links(),
) -> str:
    """O HTML da página de um jogador, com todos os seus Resultados."""
    rows = "".join(_result_row(tournament, standing, config, links) for tournament, standing in _ordered(results))
    aliases = ", ".join(escape(username) for username in usernames)
    body = (
        f'<header class="hero"><h1>{escape(person)}</h1>'
        f'<p class="considered">{aliases}</p></header>'
        "<section><h2>Resultados</h2><table><thead><tr>"
        "<th>Data</th><th>Torneio</th><th>Posição</th><th>Score</th><th>Performance</th><th>Partidas</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></section>"
    )
    return _layout(title=person, body=_nav(links) + "\n" + body, base=links.base)


def _title(ranking: Ranking) -> str:
    scope = ranking.scope
    window = f"Temporada {scope.value}" if scope.kind == "season" else f"Recorte {scope.value}"
    return f"Ranking — {window}"


def _nav(links: Links) -> str:
    return (
        '<nav class="nav">'
        f'<a href="{links.ranking()}">Ranking</a>'
        f'<a href="{links.tournaments()}">Torneios</a>'
        "</nav>"
    )


def _layout(*, title: str, body: str, base: str = "") -> str:
    return _LAYOUT.substitute(title=escape(title), body=body, base=base)


def _hero(ranking: Ranking) -> str:
    scope = ranking.scope
    return (
        '<header class="hero">'
        "<h1>Arena dos Cavaleiros</h1>"
        f'<p class="window">{escape(_title(ranking))} — {scope.starts_at} a {scope.ends_at}</p>'
        f'<p class="considered">{ranking.tournaments_considered} torneio(s) considerado(s), '
        f"melhores N = {ranking.best_n}</p>"
        "</header>"
    )


def _rules(config: Config, ranking: Ranking) -> str:
    best = config.ranking.best_n
    eligibility = config.ranking.eligibility.min_participation_fraction
    minimum = config.ranking.min_tournaments_for_champion
    tie_break = " → ".join(_TIE_LABELS[name] for name in config.ranking.tie_break)
    items = (
        f"<li><strong>Melhores N:</strong> só contam os melhores {best.fraction:.0%} "
        f"dos Resultados do período (arredondando para {_ROUNDING_LABELS[best.rounding]}); "
        f"neste período, N = {ranking.best_n}.</li>"
        f"<li><strong>Elegibilidade a prêmio:</strong> presença em pelo menos "
        f"{eligibility:.0%} dos Torneios Válidos.</li>"
        f"<li><strong>Campeão:</strong> o período precisa de ao menos {minimum} Torneios "
        "Válidos, e o título vai para o melhor jogador elegível.</li>"
        f"<li><strong>Desempate:</strong> {tie_break}.</li>"
    )
    return (
        '<section class="rules"><h2>Como o Ranking é calculado</h2>'
        f"<ul>{items}</ul></section>"
    )


def _podium(ranking: Ranking, config: Config) -> str:
    if not ranking.champion_elected:
        minimum = config.ranking.min_tournaments_for_champion
        if ranking.tournaments_considered < minimum:
            reason = f"são necessários ao menos {minimum} Torneios Válidos"
        else:
            reason = "nenhum jogador tem presença suficiente"
        return f'<section class="podium empty"><p>Sem campeão eleito: {escape(reason)}.</p></section>'

    champion = ranking.champion
    cards = []
    for position, row in enumerate(ranking.rows[:3], start=1):
        badge = ' <span class="badge">Campeão</span>' if row is champion else ""
        cards.append(
            f'<li class="podium-{position}"><span class="place">{position}º</span> '
            f'<span class="name">{escape(row.person)}</span> '
            f'<span class="points">{row.total}</span>{badge}</li>'
        )
    return '<section class="podium"><h2>Pódio</h2><ol>' + "".join(cards) + "</ol></section>"


def _table(ranking: Ranking, links: Links) -> str:
    header = (
        "<tr><th>#</th><th>Jogador</th><th>Total</th><th>Contados</th>"
        "<th>Descartados</th><th>Presença</th><th>1º</th><th>Melhor</th><th>Elegível</th></tr>"
    )
    rows = "".join(_table_row(row, links) for row in ranking.rows)
    return (
        '<section class="ranking"><h2>Ranking</h2>'
        f"<table><thead>{header}</thead><tbody>{rows}</tbody></table></section>"
    )


def _table_row(row: RankingRow, links: Links) -> str:
    aliases = ""
    if len(row.usernames) > 1:
        aliases = f' <span class="aliases">({escape(", ".join(row.usernames))})</span>'
    breakdown = "".join(
        f'<li class="{"counted" if entry.counted else "discarded"}">'
        f"{escape(entry.tournament_id)}: {entry.score}</li>"
        for entry in row.breakdown
    )
    return (
        f'<tr><td class="rank">{row.rank}</td>'
        f'<td class="person"><a href="{links.player(row.person)}">{escape(row.person)}</a>{aliases}'
        f'<details><summary>Resultados</summary><ul class="breakdown">{breakdown}</ul></details></td>'
        f'<td class="total">{row.total}</td>'
        f"<td>{row.counted}</td>"
        f"<td>{row.played - row.counted}</td>"
        f"<td>{row.participation:.0%}</td>"
        f"<td>{row.first_places}</td>"
        f"<td>{row.best_single_score}</td>"
        f'<td>{"sim" if row.eligible else "não"}</td></tr>'
    )


def _tournament_row(
    tournament: ArchivedTournament, config: Config, links: Links, resolver: Resolver
) -> str:
    day = local_date(tournament.starts_at, config.seasons.timezone)
    winner = _winner(tournament)
    if winner is None:
        winner_html = "—"
    else:
        person = resolver.person(winner.username)
        winner_html = f'<a href="{links.player(person)}">{escape(person)}</a>'
    return (
        f"<tr><td>{day}</td>"
        f"<td>{tournament.edition}</td>"
        f'<td><a href="{links.tournament(tournament.id)}">{escape(tournament.name)}</a></td>'
        f"<td>{tournament.nb_players}</td>"
        f"<td>{tournament.games}</td>"
        f"<td>{winner_html}</td></tr>"
    )


def _standing_row(standing: ArchivedStanding, links: Links, resolver: Resolver) -> str:
    person = resolver.person(standing.username)
    performance = standing.performance if standing.performance is not None else "—"
    return (
        f'<tr><td class="rank">{standing.rank}</td>'
        f'<td class="person"><a href="{links.player(person)}">{escape(standing.username)}</a></td>'
        f'<td class="total">{standing.score}</td>'
        f"<td>{performance}</td>"
        f"<td>{standing.games}</td></tr>"
    )


def _result_row(
    tournament: ArchivedTournament, standing: ArchivedStanding, config: Config, links: Links
) -> str:
    day = local_date(tournament.starts_at, config.seasons.timezone)
    performance = standing.performance if standing.performance is not None else "—"
    return (
        f"<tr><td>{day}</td>"
        f'<td><a href="{links.tournament(tournament.id)}">{escape(tournament.name)}</a></td>'
        f'<td class="rank">{standing.rank}</td>'
        f'<td class="total">{standing.score}</td>'
        f"<td>{performance}</td>"
        f"<td>{standing.games}</td></tr>"
    )


def _recortes(recortes: Sequence[Scope], links: Links) -> str:
    if not recortes:
        return ""
    items = "".join(
        f'<li><a href="{links.recorte(scope.value)}">{escape(_scope_label(scope))}</a> '
        f'<span class="aliases">{scope.starts_at} a {scope.ends_at}</span></li>'
        for scope in recortes
    )
    return f'<section class="recortes"><h2>Recortes</h2><ul>{items}</ul></section>'


def _scope_label(scope: Scope) -> str:
    if scope.kind == "month":
        return f"Mês {scope.value}"
    if scope.kind == "semester":
        return f"Semestre {scope.value}"
    return f"Temporada {scope.value}"


def _data_file(ranking: Ranking) -> str:
    if ranking.scope.kind == "season":
        return RANKING_FILE
    return f"{RECORTE_PAGES_DIR}/{ranking.scope.value}.json"


def _footer(ranking: Ranking, links: Links) -> str:
    data_file = _data_file(ranking)
    return (
        '<footer class="foot">'
        f"<p>Gerado em {_iso(ranking.generated_at)}. Dados derivados: "
        f'<a href="{links.url(data_file)}">{data_file}</a>, '
        f'<a href="{links.url(TOURNAMENTS_JSON)}">{TOURNAMENTS_JSON}</a>, '
        f'<a href="{links.url(PLAYERS_JSON)}">{PLAYERS_JSON}</a>.</p>'
        "</footer>"
    )


def _winner(tournament: ArchivedTournament) -> ArchivedStanding | None:
    for standing in sorted(tournament.standings, key=lambda item: (item.rank, item.username)):
        if standing.rank == 1:
            return standing
    return None


def _players(
    tournaments: Sequence[ArchivedTournament], resolver: Resolver
) -> dict[str, list[tuple[ArchivedTournament, ArchivedStanding]]]:
    players: dict[str, list[tuple[ArchivedTournament, ArchivedStanding]]] = {}
    for tournament in tournaments:
        for standing in tournament.standings:
            players.setdefault(resolver.person(standing.username), []).append((tournament, standing))
    return players


def _ordered(
    results: Sequence[tuple[ArchivedTournament, ArchivedStanding]],
) -> list[tuple[ArchivedTournament, ArchivedStanding]]:
    return sorted(results, key=lambda item: (item[0].starts_at, item[0].id))


def _recorte_scopes(
    config: Config, season: Season, tournaments: Sequence[ArchivedTournament]
) -> list[Scope]:
    """Os meses e semestres com ao menos um Torneio Válido, recortados pela Temporada."""
    months: set[str] = set()
    semesters: set[str] = set()
    for tournament in tournaments:
        day = local_date(tournament.starts_at, config.seasons.timezone)
        months.add(f"{day.year:04d}-{day.month:02d}")
        semesters.add(f"{day.year:04d}-H{1 if day.month <= 6 else 2}")
    scopes = [month_scope(season, value) for value in sorted(months)]
    scopes += [semester_scope(season, value) for value in sorted(semesters)]
    return scopes


def _slugs(persons: Iterable[str]) -> dict[str, str]:
    used: dict[str, int] = {}
    slugs: dict[str, str] = {}
    for person in sorted(persons):
        base = _slug(person)
        count = used.get(base, 0)
        used[base] = count + 1
        slugs[person] = base if count == 0 else f"{base}-{count + 1}"
    return slugs


def _slug(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_name).strip("-").lower()
    return slug or "jogador"


def _tournaments_payload(
    tournaments: Sequence[ArchivedTournament], resolver: Resolver, moment: datetime
) -> dict[str, Any]:
    return {
        "generatedAt": _iso(moment),
        "tournaments": [
            {
                "id": tournament.id,
                "name": tournament.name,
                "edition": tournament.edition,
                "startsAt": _iso(tournament.starts_at),
                "finishesAt": _iso(tournament.finishes_at),
                "nbPlayers": tournament.nb_players,
                "games": tournament.games,
                "winner": _winner_ref(tournament, resolver),
            }
            for tournament in tournaments
        ],
    }


def _winner_ref(tournament: ArchivedTournament, resolver: Resolver) -> dict[str, str] | None:
    winner = _winner(tournament)
    if winner is None:
        return None
    return {"username": winner.username, "person": resolver.person(winner.username)}


def _players_payload(
    players: Mapping[str, Sequence[tuple[ArchivedTournament, ArchivedStanding]]],
    resolver: Resolver,
    moment: datetime,
) -> dict[str, Any]:
    return {
        "generatedAt": _iso(moment),
        "players": [
            {
                "person": person,
                "usernames": list(resolver.usernames(person)),
                "results": [
                    {
                        "tournamentId": tournament.id,
                        "startsAt": _iso(tournament.starts_at),
                        "rank": standing.rank,
                        "score": standing.score,
                        "performance": standing.performance,
                        "games": standing.games,
                    }
                    for tournament, standing in _ordered(results)
                ],
            }
            for person, results in sorted(players.items())
        ],
    }


def _write(path: Path, text: str) -> Path:
    """Grava o arquivo; não reescreve quando o conteúdo não mudou."""
    path = Path(path)
    data = text.encode("utf-8")
    if not (path.is_file() and path.read_bytes() == data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return path


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _iso(instant: datetime) -> str:
    return instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


_LAYOUT = Template(
    """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<link rel="stylesheet" href="${base}assets/style.css">
</head>
<body>
<main>
$body
</main>
</body>
</html>
"""
)


STYLE = """\
:root {
  --bg: #0f1115;
  --fg: #e8e8ea;
  --muted: #9aa0a6;
  --accent: #f0b429;
  --card: #1a1d23;
  --line: #2a2e37;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  line-height: 1.5;
}
main { max-width: 900px; margin: 0 auto; padding: 1rem 1rem 4rem; }
a { color: var(--accent); }
.nav { display: flex; gap: 1rem; padding: 1rem 0; border-bottom: 1px solid var(--line); }
.nav a { text-decoration: none; font-weight: 600; }
.hero h1 { margin: 1.5rem 0 0.25rem; font-size: 1.8rem; }
.window { color: var(--accent); margin: 0; }
.considered { color: var(--muted); margin: 0.25rem 0 0; }
h2 { margin-top: 2rem; border-bottom: 1px solid var(--line); padding-bottom: 0.3rem; }
.rules ul { color: var(--muted); }
.recortes ul { list-style: none; padding: 0; }
.recortes li { padding: 0.25rem 0; }
.podium ol {
  list-style: none;
  padding: 0;
  display: grid;
  gap: 0.5rem;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}
.podium li {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 1rem;
}
.podium .place { color: var(--accent); font-weight: 700; margin-right: 0.5rem; }
.podium .points { float: right; color: var(--muted); }
.badge {
  display: inline-block;
  margin-left: 0.5rem;
  background: var(--accent);
  color: #111;
  border-radius: 999px;
  padding: 0.05rem 0.5rem;
  font-size: 0.75rem;
  font-weight: 700;
}
.podium.empty {
  color: var(--muted);
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 1rem;
}
table { width: 100%; border-collapse: collapse; margin-top: 1rem; font-variant-numeric: tabular-nums; }
th, td { text-align: right; padding: 0.45rem 0.5rem; border-bottom: 1px solid var(--line); }
th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) { text-align: left; }
.person { min-width: 12rem; }
.aliases { color: var(--muted); font-size: 0.85rem; }
details { margin-top: 0.2rem; }
summary { cursor: pointer; color: var(--muted); font-size: 0.8rem; }
.breakdown { list-style: none; padding: 0.25rem 0 0; margin: 0; font-size: 0.8rem; color: var(--muted); }
.breakdown .counted::before { content: "\\2713 "; color: #6bd38a; }
.breakdown .discarded { text-decoration: line-through; opacity: 0.6; }
.breakdown .discarded::before { content: "\\2717 "; }
.foot { margin-top: 3rem; color: var(--muted); font-size: 0.85rem; }
@media (max-width: 640px) {
  table { font-size: 0.85rem; }
  th:nth-child(7), td:nth-child(7), th:nth-child(8), td:nth-child(8) { display: none; }
}
"""
