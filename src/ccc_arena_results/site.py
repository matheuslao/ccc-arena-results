"""O site: a página estática, pré-renderizada dos dados derivados.

O site é a leitura pública do Ranking. Ele recebe o Ranking já calculado e nunca
consulta o Lichess — por isso continua no ar com a API fora. As páginas são HTML
pré-renderizado, sem framework de front-end; os dados derivados em JSON são
publicados junto, para qualquer consumidor futuro (ver ADR-0003).

O layout é um ``string.Template``; o corpo é montado por funções puras, com todo
texto vindo dos dados escapado. Gerar o site não toca a rede: a única entrada é
o arquivo canônico já coletado.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from string import Template
from typing import Any

from .archive import ArchivedTournament
from .config import Config
from .rank import Ranking, RankingRow
from .rank import build as build_ranking
from .season import scope_for

__all__ = ["Site", "build", "render_ranking_page"]

INDEX_FILE = "index.html"
RANKING_FILE = "ranking.json"
STYLE_FILE = "assets/style.css"

_TIE_LABELS = {
    "firstPlaces": "mais primeiros lugares",
    "bestSingleScore": "melhor Resultado individual",
    "tournamentsPlayed": "mais torneios jogados",
}

_ROUNDING_LABELS = {"ceil": "cima", "floor": "baixo", "round": "o mais próximo"}


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
    scope = scope_for(config, season_label=season_label)
    ranking = build_ranking(config, tournaments, scope, now=now)
    output_dir = Path(output_dir)
    written = (
        _write(output_dir / INDEX_FILE, render_ranking_page(ranking, config)),
        _write(output_dir / RANKING_FILE, _json(ranking.to_payload())),
        _write(output_dir / STYLE_FILE, STYLE),
    )
    return Site(output_dir=output_dir, ranking=ranking, written=tuple(written))


def render_ranking_page(ranking: Ranking, config: Config) -> str:
    """O HTML da página de Ranking de uma janela."""
    body = "\n".join(
        (
            _hero(ranking),
            _rules(config, ranking),
            _podium(ranking, config),
            _table(ranking),
            _footer(ranking),
        )
    )
    return _LAYOUT.substitute(title=_title(ranking), body=body)


def _title(ranking: Ranking) -> str:
    scope = ranking.scope
    window = f"Temporada {scope.value}" if scope.kind == "season" else f"Recorte {scope.value}"
    return f"Ranking — {window}"


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


def _table(ranking: Ranking) -> str:
    header = (
        "<tr><th>#</th><th>Jogador</th><th>Total</th><th>Contados</th>"
        "<th>Descartados</th><th>Presença</th><th>1º</th><th>Melhor</th><th>Elegível</th></tr>"
    )
    rows = "".join(_table_row(row) for row in ranking.rows)
    return (
        '<section class="ranking"><h2>Ranking</h2>'
        f"<table><thead>{header}</thead><tbody>{rows}</tbody></table></section>"
    )


def _table_row(row: RankingRow) -> str:
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
        f'<td class="person">{escape(row.person)}{aliases}'
        f'<details><summary>Resultados</summary><ul class="breakdown">{breakdown}</ul></details></td>'
        f'<td class="total">{row.total}</td>'
        f"<td>{row.counted}</td>"
        f"<td>{row.played - row.counted}</td>"
        f"<td>{row.participation:.0%}</td>"
        f"<td>{row.first_places}</td>"
        f"<td>{row.best_single_score}</td>"
        f'<td>{"sim" if row.eligible else "não"}</td></tr>'
    )


def _footer(ranking: Ranking) -> str:
    generated = (
        ranking.generated_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    return (
        '<footer class="foot">'
        f"<p>Gerado em {generated}. "
        f'Os dados derivados estão em <a href="{RANKING_FILE}">{RANKING_FILE}</a>.</p>'
        "</footer>"
    )


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


_LAYOUT = Template(
    """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<link rel="stylesheet" href="assets/style.css">
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
main { max-width: 900px; margin: 0 auto; padding: 2rem 1rem 4rem; }
a { color: var(--accent); }
.hero h1 { margin: 0 0 0.25rem; font-size: 1.8rem; }
.window { color: var(--accent); margin: 0; }
.considered { color: var(--muted); margin: 0.25rem 0 0; }
h2 { margin-top: 2rem; border-bottom: 1px solid var(--line); padding-bottom: 0.3rem; }
.rules ul { color: var(--muted); }
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
