"""O site: as páginas estáticas, pré-renderizadas dos dados derivados.

O site é a leitura pública do Ranking, dos Torneios e dos Jogadores. Ele recebe
os torneios já arquivados e nunca consulta o Lichess — por isso continua no ar
com a API fora. As páginas são HTML pré-renderizado, sem framework de front-end;
os dados derivados em JSON são publicados junto, para qualquer consumidor futuro
(ver ADR-0003).

A identidade visual vem da logo dos Cavaleiros do Centro (xilogravura: tinta
sobre pergaminho, com sol dourado), traduzida em variáveis de CSS. O layout é um
``string.Template``; o corpo é montado por funções puras, com todo texto vindo
dos dados escapado. Gerar o site não toca a rede.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from html import escape
from pathlib import Path
from string import Template
from typing import Any

from .aliases import Resolver
from .archive import ArchivedStanding, ArchivedTournament
from .charts import Bar, Series, bar_chart, line_chart
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
LOGO_FILE = "assets/logo.png"
TOURNAMENT_PAGES_DIR = "torneio"
PLAYER_PAGES_DIR = "jogador"
RECORTE_PAGES_DIR = "recorte"

LICHESS_TOURNAMENT_URL = "https://lichess.org/tournament/{id}"

_LOGO_SRC = Path(__file__).with_name("logo.png")

_TIE_LABELS = {
    "firstPlaces": "mais primeiros lugares",
    "bestSingleScore": "melhor Resultado individual",
    "tournamentsPlayed": "mais torneios jogados",
}

_ROUNDING_LABELS = {"ceil": "cima", "floor": "baixo", "round": "o mais próximo"}

_MONTH_NAMES = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)

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
            render_ranking_page(
                ranking, config, Links("", slugs), recortes, section="ranking"
            ),
        ),
        _write(output_dir / RANKING_FILE, _json(ranking.to_payload())),
        _write(
            output_dir / TOURNAMENTS_FILE,
            render_tournaments_page(selected, config, Links("", slugs), resolver, section="torneios"),
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
                render_ranking_page(
                    recorte_ranking, config, Links("../", slugs), section="ranking"
                ),
            )
        )
        written.append(
            _write(
                output_dir / RECORTE_PAGES_DIR / f"{recorte.value}.json",
                _json(recorte_ranking.to_payload()),
            )
        )
    written.append(_write(output_dir / STYLE_FILE, STYLE))
    written.append(_write_bytes(output_dir / LOGO_FILE, _LOGO_SRC.read_bytes()))
    return Site(output_dir=output_dir, ranking=ranking, written=tuple(written))


def render_ranking_page(
    ranking: Ranking,
    config: Config,
    links: Links = Links(),
    recortes: Sequence[Scope] = (),
    *,
    section: str | None = None,
) -> str:
    """O HTML da página de Ranking de uma janela."""
    body = "\n".join(
        (
            _ranking_hero(ranking),
            _rules(config, ranking),
            _podium(ranking, config),
            _table(ranking, links),
            _recortes(recortes, links),
            _footer(ranking, links),
        )
    )
    return _layout(
        title=_title(ranking), top=_top(links, section), body=body, base=links.base
    )


def render_tournaments_page(
    tournaments: Sequence[ArchivedTournament],
    config: Config,
    links: Links = Links(),
    resolver: Resolver = _IDENTITY,
    *,
    section: str | None = None,
) -> str:
    """O HTML da lista de Torneios Válidos."""
    rows = "".join(
        _tournament_row(tournament, config, links, resolver)
        for tournament in _recent_first(tournaments)
    )
    body = "\n".join(
        (
            _simple_hero(
                eyebrow="Arena dos Cavaleiros",
                title="Torneios",
                subtitle=f"{len(tournaments)} Torneio(s) Válido(s)",
            ),
            _table_wrap(
                "<tr><th>Data</th><th>Edição</th><th>Torneio</th>"
                "<th>Jogadores</th><th>Partidas</th><th>Vencedor</th>"
                "<th>Lichess</th></tr>",
                rows,
            ),
            _footer_links(links),
        )
    )
    return _layout(title="Torneios", top=_top(links, section), body=body, base=links.base)


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
    body = "\n".join(
        (
            _simple_hero(
                eyebrow=f"Edição {tournament.edition} — {_long_date(day)}",
                title=tournament.name,
                subtitle=f"{tournament.nb_players} jogadores, {tournament.games} partidas",
            ),
            _tournament_chart(tournament, resolver),
            '<section><h2>Classificação final</h2>'
            + _table_wrap(
                "<tr><th>#</th><th>Jogador</th><th>Score</th>"
                "<th>Performance</th><th>Partidas</th></tr>",
                rows,
            )
            + "</section>",
            _footer_links(links),
        )
    )
    return _layout(title=tournament.name, top=_top(links, None), body=body, base=links.base)


def render_player_page(
    person: str,
    usernames: Sequence[str],
    results: Sequence[tuple[ArchivedTournament, ArchivedStanding]],
    config: Config,
    links: Links = Links(),
) -> str:
    """O HTML da página de um jogador, com todos os seus Resultados."""
    ordered = _ordered(results)
    rows = "".join(
        _result_row(tournament, standing, config, links)
        for tournament, standing in reversed(ordered)
    )
    aliases = ", ".join(escape(username) for username in usernames)
    body = "\n".join(
        (
            _simple_hero(eyebrow="Jogador", title=person, subtitle=aliases),
            _player_score_chart(person, ordered, config),
            _player_position_chart(person, ordered, config),
            '<section><h2>Resultados</h2>'
            + _table_wrap(
                "<tr><th>Data</th><th>Torneio</th><th>Posição</th>"
                "<th>Score</th><th>Performance</th><th>Partidas</th></tr>",
                rows,
            )
            + "</section>",
            _footer_links(links),
        )
    )
    return _layout(title=person, top=_top(links, None), body=body, base=links.base)


def _title(ranking: Ranking) -> str:
    scope = ranking.scope
    if scope.kind == "season":
        return f"Ranking — Temporada {scope.value}"
    return f"Ranking — {_scope_name(scope)}"


def _top(links: Links, section: str | None) -> str:
    def current(name: str) -> str:
        return ' aria-current="page"' if section == name else ""

    return (
        '<header class="top"><div class="wrap">'
        f'<a class="brand" href="{links.ranking()}">'
        f'<img src="{links.url(LOGO_FILE)}" alt="" width="44" height="44">'
        "<span>Arena dos Cavaleiros</span></a>"
        '<nav class="nav">'
        f'<a href="{links.ranking()}"{current("ranking")}>Ranking</a>'
        f'<a href="{links.tournaments()}"{current("torneios")}>Torneios</a>'
        "</nav></div></header>"
    )


def _layout(*, title: str, top: str, body: str, base: str = "") -> str:
    return _LAYOUT.substitute(title=escape(title), top=top, body=body, base=base)


def _ranking_hero(ranking: Ranking) -> str:
    scope = ranking.scope
    return (
        '<section class="hero">'
        f'<p class="eyebrow">{escape(_scope_kind_label(scope))}</p>'
        f"<h1>{escape(_scope_title(scope))}</h1>"
        f'<p class="period">{escape(_long_range(scope.starts_at, scope.ends_at))}</p>'
        '<ul class="stats">'
        f'<li><span class="n">{ranking.tournaments_considered}</span>torneios</li>'
        f'<li><span class="n">{ranking.best_n}</span>melhores por jogador</li>'
        "</ul></section>"
    )


def _simple_hero(*, eyebrow: str, title: str, subtitle: str) -> str:
    return (
        '<section class="hero">'
        f'<p class="eyebrow">{escape(eyebrow)}</p>'
        f"<h1>{escape(title)}</h1>"
        f'<p class="window">{escape(subtitle)}</p>'
        "</section>"
    )


def _rules(config: Config, ranking: Ranking) -> str:
    best = config.ranking.best_n
    eligibility = config.ranking.eligibility.min_participation_fraction
    minimum = config.ranking.min_tournaments_for_champion
    tie_break = " → ".join(_TIE_LABELS[name] for name in config.ranking.tie_break)
    total = ranking.tournaments_considered
    n = ranking.best_n
    if total > 0:
        best_item = (
            f"<li><strong>Melhores N:</strong> cada jogador soma apenas os seus "
            f"<strong>{n} melhores</strong> Resultados dos <strong>{total}</strong> torneios "
            f"do período — os piores ficam de fora. A regra é {best.fraction:.0%} dos "
            f"torneios, arredondada para {_ROUNDING_LABELS[best.rounding]}; quem jogou menos "
            f"de {n} conta com todos os Resultados. {_n_meter(n, total)}</li>"
        )
    else:
        best_item = (
            f"<li><strong>Melhores N:</strong> cada jogador soma apenas os seus melhores "
            f"Resultados do período — {best.fraction:.0%} dos torneios, arredondados para "
            f"{_ROUNDING_LABELS[best.rounding]}.</li>"
        )
    items = (
        best_item
        + f"<li><strong>Elegibilidade ao pódio:</strong> presença em pelo menos "
        f"{eligibility:.0%} dos Torneios Válidos.</li>"
        f"<li><strong>Campeão:</strong> o período precisa de ao menos {minimum} Torneios "
        "Válidos, e o título vai para o melhor jogador elegível.</li>"
        f"<li><strong>Desempate:</strong> {tie_break}.</li>"
    )
    return (
        '<section class="card rules"><h2>Como o Ranking é calculado</h2>'
        f"<ul>{items}</ul></section>"
    )


def _n_meter(n: int, total: int) -> str:
    """Uma barrinha que mostra quantos, dos torneios do período, contam na soma."""
    if total <= 0 or n <= 0:
        return ""
    pct = min(100.0, 100.0 * n / total)
    return (
        f'<span class="meter" role="img" aria-label="{n} de {total} torneios contam">'
        f'<span class="meter-fill" style="width:{pct:.0f}%"></span></span>'
    )


def _podium(ranking: Ranking, config: Config) -> str:
    if not ranking.champion_elected:
        minimum = config.ranking.min_tournaments_for_champion
        if ranking.tournaments_considered < minimum:
            reason = f"são necessários ao menos {minimum} Torneios Válidos"
        else:
            reason = "nenhum jogador tem presença suficiente"
        return f'<section class="podium empty card"><p>Sem campeão eleito: {escape(reason)}.</p></section>'

    champion = ranking.champion
    # Só quem tem presença suficiente concorre ao título; o pódio são os elegíveis.
    eligible = [row for row in ranking.rows if row.eligible][:3]
    cards = []
    for position, row in enumerate(eligible, start=1):
        badge = ' <span class="badge">Campeão</span>' if row is champion else ""
        cards.append(
            f'<li class="podium-{position}"><span class="place">{position}º</span> '
            f'<span class="name">{escape(row.person)}</span> '
            f'<span class="points">{row.total}</span>{badge}</li>'
        )
    note = (
        '<p class="podium-note">Só concorre ao título quem tem presença suficiente no '
        "período; por isso o campeão pode não ser o líder da tabela.</p>"
    )
    return (
        '<section class="podium"><h2>Pódio</h2><ol>'
        + "".join(cards)
        + "</ol>"
        + note
        + "</section>"
    )


def _table(ranking: Ranking, links: Links) -> str:
    header = (
        '<tr><th title="Posição no Ranking">#</th>'
        "<th>Jogador</th>"
        '<th title="Soma dos Resultados que contam">Pontos</th>'
        '<th title="Quantos Resultados do jogador entram na soma">Contam</th>'
        '<th title="Resultados deixados de fora (os piores, além dos N melhores)">'
        "Descartados</th>"
        '<th title="Torneios jogados ÷ torneios do período">Presença</th>'
        '<th title="Primeiros lugares (torneios vencidos)">1ºs</th>'
        '<th title="Melhor Resultado individual no período">Melhor</th>'
        '<th title="Tem presença suficiente para concorrer ao pódio">Elegível</th></tr>'
    )
    champion = ranking.champion
    rows = "".join(_table_row(row, links, champion) for row in ranking.rows)
    help_text = (
        '<p class="table-help">Pontos = soma dos Resultados que contam · '
        "Contam / Descartados = quantos entram na soma e quantos ficam de fora · "
        "Presença = torneios jogados ÷ torneios do período.</p>"
    )
    return (
        '<section class="ranking-sec"><h2>Ranking</h2>'
        + help_text
        + _table_wrap(header, rows, table_class="ranking")
        + "</section>"
    )


def _table_wrap(header: str, rows: str, *, table_class: str = "") -> str:
    klass = f' class="{table_class}"' if table_class else ""
    return (
        '<div class="table-wrap">'
        f"<table{klass}><thead>{header}</thead><tbody>{rows}</tbody></table></div>"
    )


def _table_row(row: RankingRow, links: Links, champion: RankingRow | None = None) -> str:
    aliases = ""
    if len(row.usernames) > 1:
        aliases = f' <span class="aliases">({escape(", ".join(row.usernames))})</span>'
    breakdown = "".join(
        f'<li class="{"counted" if entry.counted else "discarded"}">'
        f"{escape(entry.tournament_id)}: {entry.score}</li>"
        for entry in row.breakdown
    )
    crown = (
        ' <span class="badge">Campeão</span>'
        if champion is not None and row.person == champion.person
        else ""
    )
    medal = f" rank-{row.rank}" if row.rank <= 3 else ""
    return (
        f'<tr><td class="rank{medal}" data-label="#">{row.rank}</td>'
        f'<td class="person" data-label="Jogador">'
        f'<a href="{links.player(row.person)}">{escape(row.person)}</a>{aliases}{crown}'
        f'<details><summary>Resultados</summary><ul class="breakdown">{breakdown}</ul></details></td>'
        f'<td class="total" data-label="Pontos">{row.total}</td>'
        f'<td data-label="Contam">{row.counted}</td>'
        f'<td data-label="Descartados">{row.played - row.counted}</td>'
        f'<td data-label="Presença">{row.participation:.0%}</td>'
        f'<td data-label="1ºs">{row.first_places}</td>'
        f'<td data-label="Melhor">{row.best_single_score}</td>'
        f'<td data-label="Elegível">{"sim" if row.eligible else "não"}</td></tr>'
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
        f"<tr><td>{_numeric_date(day)}</td>"
        f"<td>{tournament.edition}</td>"
        f'<td class="person"><a href="{links.tournament(tournament.id)}">{escape(tournament.name)}</a></td>'
        f"<td>{tournament.nb_players}</td>"
        f"<td>{tournament.games}</td>"
        f"<td>{winner_html}</td>"
        f'<td><a class="external" href="{_lichess_url(tournament.id)}" target="_blank" '
        f'rel="noopener" title="Ver o torneio no Lichess">abrir ↗</a></td></tr>'
    )


def _standing_row(standing: ArchivedStanding, links: Links, resolver: Resolver) -> str:
    person = resolver.person(standing.username)
    performance = standing.performance if standing.performance is not None else "—"
    medal = f" rank-{standing.rank}" if standing.rank <= 3 else ""
    return (
        f'<tr><td class="rank{medal}">{standing.rank}</td>'
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
    medal = f" rank-{standing.rank}" if standing.rank <= 3 else ""
    return (
        f"<tr><td>{_numeric_date(day)}</td>"
        f'<td class="person"><a href="{links.tournament(tournament.id)}">{escape(tournament.name)}</a></td>'
        f'<td class="rank{medal}">{standing.rank}</td>'
        f'<td class="total">{standing.score}</td>'
        f"<td>{performance}</td>"
        f"<td>{standing.games}</td></tr>"
    )


def _recortes(recortes: Sequence[Scope], links: Links) -> str:
    if not recortes:
        return ""
    items = "".join(
        f'<li><a href="{links.recorte(scope.value)}">{escape(_scope_name(scope))}'
        f'<span class="aliases">{escape(_long_range(scope.starts_at, scope.ends_at))}</span></a></li>'
        for scope in recortes
    )
    return f'<section class="recortes"><h2>Recortes</h2><ul>{items}</ul></section>'


def _scope_name(scope: Scope) -> str:
    """O nome humano da janela: 'Setembro de 2026', '2º semestre de 2026'."""
    if scope.kind == "month":
        year, month = scope.value.split("-")
        return f"{_month_name(int(month)).capitalize()} de {year}"
    if scope.kind == "semester":
        year, half = scope.value.split("-H")
        return f"{half}º semestre de {year}"
    return f"Temporada {scope.value}"


def _scope_title(scope: Scope) -> str:
    """O título da janela, deixando claro se é a Temporada ou um Recorte."""
    if scope.kind == "season":
        return f"Temporada {scope.value}"
    return f"Recorte — {_scope_name(scope)}"


def _scope_kind_label(scope: Scope) -> str:
    if scope.kind == "month":
        return "Ranking do recorte mensal"
    if scope.kind == "semester":
        return "Ranking do recorte semestral"
    return "Ranking da temporada"


def _month_name(month: int) -> str:
    return _MONTH_NAMES[month - 1]


def _long_date(day: date) -> str:
    return f"{day.day} de {_month_name(day.month)} de {day.year}"


def _numeric_date(day: date) -> str:
    return f"{day.day:02d}/{day.month:02d}/{day.year}"


def _lichess_url(tournament_id: str) -> str:
    return LICHESS_TOURNAMENT_URL.format(id=tournament_id)


def _long_range(starts_at: date, ends_at: date) -> str:
    """Um intervalo de datas em português, do mais curto ao mais explícito."""
    if starts_at == ends_at:
        return _long_date(starts_at)
    if (starts_at.year, starts_at.month) == (ends_at.year, ends_at.month):
        return (
            f"{starts_at.day} a {ends_at.day} de "
            f"{_month_name(ends_at.month)} de {ends_at.year}"
        )
    if starts_at.year == ends_at.year and starts_at.month == 1 and ends_at.month == 12:
        if starts_at.day == 1 and ends_at.day == 31:
            return f"todo o ano de {ends_at.year}"
    if starts_at.year == ends_at.year:
        return (
            f"{starts_at.day} de {_month_name(starts_at.month)} a "
            f"{ends_at.day} de {_month_name(ends_at.month)} de {ends_at.year}"
        )
    return f"{_long_date(starts_at)} a {_long_date(ends_at)}"


def _data_file(ranking: Ranking) -> str:
    if ranking.scope.kind == "season":
        return RANKING_FILE
    return f"{RECORTE_PAGES_DIR}/{ranking.scope.value}.json"


def _footer(ranking: Ranking, links: Links) -> str:
    data_file = _data_file(ranking)
    return (
        '<footer class="foot">'
        f"<p>Gerado em {_iso(ranking.generated_at)}. Dados extraídos do Lichess e "
        "derivados em JSON: "
        f'<a href="{links.url(data_file)}">{data_file}</a>, '
        f'<a href="{links.url(TOURNAMENTS_JSON)}">{TOURNAMENTS_JSON}</a>, '
        f'<a href="{links.url(PLAYERS_JSON)}">{PLAYERS_JSON}</a>.</p>'
        "</footer>"
    )


def _footer_links(links: Links) -> str:
    return (
        '<footer class="foot">'
        "<p>Dados extraídos do Lichess e derivados em JSON: "
        f'<a href="{links.url(TOURNAMENTS_JSON)}">{TOURNAMENTS_JSON}</a>, '
        f'<a href="{links.url(PLAYERS_JSON)}">{PLAYERS_JSON}</a>. '
        f'<a href="{links.ranking()}">Voltar ao Ranking</a>.</p>'
        "</footer>"
    )


def _player_score_chart(
    person: str,
    ordered: Sequence[tuple[ArchivedTournament, ArchivedStanding]],
    config: Config,
) -> str:
    if len(ordered) < 2:
        return ""
    labels = [_short_date(tournament.starts_at, config) for tournament, _ in ordered]
    values = tuple(float(standing.score) for _, standing in ordered)
    svg = line_chart([Series(person, values, "var(--c1)")], x_labels=labels)
    return _chart_figure("Evolução — score por torneio", svg)


def _player_position_chart(
    person: str,
    ordered: Sequence[tuple[ArchivedTournament, ArchivedStanding]],
    config: Config,
) -> str:
    if len(ordered) < 2:
        return ""
    labels = [_short_date(tournament.starts_at, config) for tournament, _ in ordered]
    values = tuple(float(standing.rank) for _, standing in ordered)
    svg = line_chart([Series(person, values, "var(--c2)")], x_labels=labels, invert_y=True)
    return _chart_figure("Posição por torneio (menor é melhor)", svg)


def _tournament_chart(tournament: ArchivedTournament, resolver: Resolver) -> str:
    top = sorted(tournament.standings, key=lambda item: (item.rank, item.username))[:10]
    if len(top) < 2:
        return ""
    bars = [
        Bar(
            resolver.person(standing.username),
            float(standing.score),
            "var(--c1)" if standing.rank == 1 else "var(--c2)",
        )
        for standing in top
    ]
    return _chart_figure(f"Pontuação — {len(top)} primeiros", bar_chart(bars))


def _chart_figure(caption: str, svg: str) -> str:
    if not svg:
        return ""
    return f'<figure class="chart card"><figcaption>{escape(caption)}</figcaption>{svg}</figure>'


def _short_date(instant: datetime, config: Config) -> str:
    day = local_date(instant, config.seasons.timezone)
    return f"{day.day:02d}/{day.month:02d}"


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


def _recent_first(tournaments: Sequence[ArchivedTournament]) -> list[ArchivedTournament]:
    """Do mais recente para o mais antigo — a lista de Torneios abre pelo último."""
    return sorted(
        tournaments,
        key=lambda tournament: (tournament.starts_at, tournament.id),
        reverse=True,
    )


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
            for tournament in _recent_first(tournaments)
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
    return _write_bytes(path, text.encode("utf-8"))


def _write_bytes(path: Path, data: bytes) -> Path:
    path = Path(path)
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
<meta name="color-scheme" content="light dark">
<title>$title</title>
<link rel="stylesheet" href="${base}assets/style.css">
<link rel="icon" href="${base}assets/logo.png">
</head>
<body>
$top
<main class="wrap">
$body
</main>
</body>
</html>
"""
)


STYLE = """\
:root {
  --bg: #f2e8ce;
  --card: #fbf5e3;
  --ink: #1b1811;
  --muted: #6b6350;
  --line: #dccfa9;
  --gold: #d9a22e;
  --gold-ink: #7a4e10;
  --silver: #a7adb5;
  --bronze: #b5793f;
  --good: #3f8f5b;
  --c1: #c98a1e;
  --c2: #2e6f6a;
  --c3: #b5502e;
  --c4: #3e5c8a;
  --c5: #6e7b3a;
  --c6: #7a4a6b;
  --shadow: 0 1px 2px rgba(27, 24, 17, 0.06), 0 10px 28px rgba(27, 24, 17, 0.07);
  --radius: 14px;
  --maxw: 960px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14110c;
    --card: #1e1a12;
    --ink: #f0e6c8;
    --muted: #b9ae90;
    --line: #3a3325;
    --gold: #e0a838;
    --gold-ink: #e8b84a;
    --silver: #b7bdc4;
    --bronze: #c98a55;
    --good: #6bd38a;
    --c1: #e0a838;
    --c2: #5fbdb2;
    --c3: #e07b54;
    --c4: #7fa3d8;
    --c5: #a8be6a;
    --c6: #c48fb0;
    --shadow: 0 1px 2px rgba(0, 0, 0, 0.4), 0 12px 34px rgba(0, 0, 0, 0.35);
  }
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  font-variant-numeric: tabular-nums;
}
a { color: var(--gold-ink); text-decoration: none; }
a:hover { text-decoration: underline; }
a:focus-visible, summary:focus-visible { outline: 2px solid var(--gold); outline-offset: 2px; border-radius: 4px; }
.wrap { max-width: var(--maxw); margin: 0 auto; padding: 0 1rem; }

/* Cabeçalho */
.top { position: sticky; top: 0; z-index: 10; background: var(--bg); border-bottom: 1px solid var(--line); }
.top .wrap { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding-top: 0.55rem; padding-bottom: 0.55rem; }
.brand { display: flex; align-items: center; gap: 0.6rem; color: var(--ink); font-weight: 700; }
.brand:hover { text-decoration: none; }
.brand img { width: 44px; height: 44px; border-radius: 10px; background: #f2e8ce; border: 1px solid var(--line); object-fit: contain; }
.brand span { font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif; font-size: 1.05rem; letter-spacing: 0.01em; }
.nav { display: flex; gap: 0.25rem; }
.nav a { padding: 0.35rem 0.75rem; border-radius: 999px; color: var(--muted); font-weight: 600; font-size: 0.92rem; }
.nav a:hover { background: var(--card); color: var(--ink); text-decoration: none; }
.nav a[aria-current="page"] { background: var(--gold); color: #1b1811; }

/* Herói */
.hero { padding: 2.2rem 0 0.5rem; }
.eyebrow { margin: 0; text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.75rem; font-weight: 700; color: var(--gold-ink); }
.hero h1 { margin: 0.25rem 0 0.3rem; font-family: Georgia, "Iowan Old Style", serif; font-size: clamp(1.8rem, 4vw, 2.6rem); line-height: 1.1; }
.window { margin: 0; color: var(--muted); }
.period { display: inline-block; margin: 0.15rem 0 0; padding: 0.3rem 0.85rem; border: 1px solid var(--line); border-radius: 999px; background: var(--card); color: var(--muted); font-size: 0.9rem; }
.stats { list-style: none; display: flex; flex-wrap: wrap; gap: 1.75rem; padding: 1rem 0 0; margin: 0; }
.stats li { color: var(--muted); font-size: 0.85rem; }
.stats .n { display: block; font-family: Georgia, serif; font-size: 1.7rem; font-weight: 700; color: var(--ink); line-height: 1.1; }

/* Seções */
section { margin-top: 2rem; }
h2 { font-family: Georgia, "Iowan Old Style", serif; font-size: 1.25rem; margin: 0 0 0.6rem; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: var(--radius); padding: 1rem 1.15rem; box-shadow: var(--shadow); }
.rules ul { margin: 0; padding-left: 1.1rem; color: var(--muted); }
.rules li { margin: 0.3rem 0; }
.rules strong { color: var(--ink); }
.meter { display: inline-block; vertical-align: middle; width: 7rem; height: 0.5rem; margin-left: 0.35rem; border-radius: 999px; background: var(--line); overflow: hidden; }
.meter-fill { display: block; height: 100%; background: var(--gold); }

/* Pódio */
.podium ol { list-style: none; display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.75rem; padding: 0; margin: 0; }
.podium li { position: relative; background: var(--card); border: 1px solid var(--line); border-top: 4px solid var(--gold); border-radius: var(--radius); padding: 1rem 1.1rem; box-shadow: var(--shadow); }
.podium-2 { border-top-color: var(--silver); }
.podium-3 { border-top-color: var(--bronze); }
.podium .place { display: inline-block; min-width: 1.7rem; height: 1.7rem; line-height: 1.7rem; text-align: center; border-radius: 999px; background: var(--gold); color: #1b1811; font-weight: 700; margin-right: 0.5rem; }
.podium-2 .place { background: var(--silver); }
.podium-3 .place { background: var(--bronze); color: #fff; }
.podium .name { font-weight: 700; }
.podium .points { float: right; color: var(--muted); }
.badge { display: inline-block; margin-left: 0.5rem; background: var(--gold); color: #1b1811; border-radius: 999px; padding: 0.05rem 0.55rem; font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; }
.podium.empty { color: var(--muted); }
.podium-note { margin: 0.6rem 0 0; color: var(--muted); font-size: 0.85rem; }

/* Tabelas */
.table-help { margin: 0 0 0.6rem; color: var(--muted); font-size: 0.82rem; }
.table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: var(--radius); background: var(--card); box-shadow: var(--shadow); }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 0.6rem 0.75rem; border-bottom: 1px solid var(--line); text-align: right; white-space: nowrap; }
th { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); font-weight: 700; }
th[title] { cursor: help; }
tbody tr:last-child td { border-bottom: 0; }
tbody tr:hover { background: rgba(217, 162, 46, 0.08); }
th:nth-child(1), td:nth-child(1), th:nth-child(2), td:nth-child(2) { text-align: left; }
.person { min-width: 12rem; white-space: normal; }
.total { font-weight: 700; }
.rank { color: var(--muted); }
.rank-1 { color: var(--gold-ink); font-weight: 700; }
.rank-2 { color: var(--silver); font-weight: 700; }
.rank-3 { color: var(--bronze); font-weight: 700; }
.aliases { color: var(--muted); font-size: 0.85rem; font-weight: 400; }
.external { white-space: nowrap; font-size: 0.85rem; }

/* Decomposição */
details { margin-top: 0.25rem; }
summary { cursor: pointer; color: var(--muted); font-size: 0.78rem; }
summary:hover { color: var(--ink); }
.breakdown { list-style: none; padding: 0.35rem 0 0; margin: 0; font-size: 0.8rem; color: var(--muted); display: flex; flex-wrap: wrap; gap: 0.3rem; }
.breakdown li { border: 1px solid var(--line); border-radius: 999px; padding: 0.05rem 0.55rem; }
.breakdown .counted { color: var(--ink); }
.breakdown .counted::before { content: "\\2713 "; color: var(--good); }
.breakdown .discarded { text-decoration: line-through; opacity: 0.6; }
.breakdown .discarded::before { content: "\\2717 "; }

/* Recortes */
.recortes ul { list-style: none; display: flex; flex-wrap: wrap; gap: 0.5rem; padding: 0; margin: 0; }
.recortes a { display: inline-flex; align-items: baseline; gap: 0.55rem; background: var(--card); border: 1px solid var(--line); border-radius: 999px; padding: 0.4rem 0.85rem; box-shadow: var(--shadow); }
.recortes a:hover { border-color: var(--gold); text-decoration: none; }
.recortes .aliases { color: var(--muted); font-size: 0.78rem; }

/* Rodapé */
.foot { margin: 3rem 0 2.5rem; padding-top: 1rem; border-top: 1px solid var(--line); color: var(--muted); font-size: 0.85rem; }

/* Gráficos */
.chart { margin: 2rem 0 0; }
.chart figcaption { font-family: Georgia, "Iowan Old Style", serif; font-size: 1.05rem; margin-bottom: 0.6rem; }
.chart-svg { display: block; width: 100%; height: auto; overflow: visible; }
.grid { stroke: var(--line); stroke-width: 1; }
.tick { fill: var(--muted); font-size: 11px; }
.chart-line { fill: none; stroke-width: 2.5; stroke-linejoin: round; stroke-linecap: round; }
.chart-dot { fill: var(--bg); stroke-width: 2; }
.bar-track { fill: var(--line); opacity: 0.5; }
.bar-label, .bar-value { fill: var(--ink); font-weight: 700; }

/* Celular: a tabela do Ranking vira uma lista de cartões */
@media (max-width: 720px) {
  .table-wrap { border: 0; background: transparent; box-shadow: none; overflow: visible; }
  table.ranking thead { display: none; }
  table.ranking, table.ranking tbody, table.ranking tr, table.ranking td { display: block; width: 100%; }
  table.ranking tr { background: var(--card); border: 1px solid var(--line); border-radius: var(--radius); margin-bottom: 0.6rem; padding: 0.4rem 0; box-shadow: var(--shadow); }
  table.ranking tr:hover { background: var(--card); }
  table.ranking td { border: 0; padding: 0.2rem 0.85rem; text-align: right; white-space: normal; }
  table.ranking td::before { content: attr(data-label); float: left; color: var(--muted); font-size: 0.8rem; }
  table.ranking td.rank { font-size: 1.05rem; border-bottom: 1px solid var(--line); padding-bottom: 0.4rem; margin-bottom: 0.3rem; }
  table.ranking td.person { text-align: left; }
  table.ranking td.person::before { display: none; }
}
"""
