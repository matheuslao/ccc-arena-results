"""Gráficos em SVG, gerados em Python.

Sem JavaScript e sem CDN: o SVG é pré-renderizado e embutido no HTML, então
funciona offline, no GitHub Pages e nos dois temas — as cores vêm de variáveis
de CSS da própria página (``var(--c1)``…). Cada gráfico é uma função pura sobre
os dados derivados; nenhuma toca a rede.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from html import escape

__all__ = ["Bar", "Series", "bar_chart", "line_chart"]

# Quanto de margem sobra para eixos e rótulos, dentro do ``viewBox``.
_PAD_LEFT = 46
_PAD_RIGHT = 14
_PAD_TOP = 12
_PAD_BOTTOM = 46


@dataclass(frozen=True)
class Series:
    """Uma linha do gráfico: rótulo, valores e a cor (variável de CSS)."""

    label: str
    values: tuple[float, ...]
    color: str = "var(--c1)"


@dataclass(frozen=True)
class Bar:
    """Uma barra: rótulo, valor e a cor (variável de CSS)."""

    label: str
    value: float
    color: str = "var(--c1)"


def line_chart(
    series: Sequence[Series],
    *,
    x_labels: Sequence[str],
    width: int = 660,
    height: int = 260,
    invert_y: bool = False,
) -> str:
    """Um gráfico de linhas sobre categorias (os ``x_labels``), em SVG.

    Com ``invert_y``, o menor valor fica no topo — é o que uma Posição pede:
    o 1º lugar em cima e o eixo crescendo para baixo. Devolve uma string vazia
    quando não há o que desenhar. O SVG é decorativo (``aria-hidden``): quem
    descreve é o ``<figcaption>``, e os mesmos dados estão nas tabelas.
    """
    if not series or not x_labels:
        return ""
    count = len(x_labels)
    plot_w = max(1, width - _PAD_LEFT - _PAD_RIGHT)
    plot_h = max(1, height - _PAD_TOP - _PAD_BOTTOM)
    values = [value for item in series for value in item.values]

    if invert_y:
        y_max = max(1.0, float(math.ceil(max(values)))) if values else 1.0
        ticks: list[float] = [float(tick) for tick in _rank_ticks(int(y_max))]

        def y(value: float) -> float:
            return _PAD_TOP + plot_h * (value - 1) / max(1.0, y_max - 1)
    else:
        y_max = (_nice_max(max(values)) if values else 0.0) or 1.0
        ticks = [y_max * step / 4 for step in range(5)]

        def y(value: float) -> float:
            return _PAD_TOP + plot_h * (1 - value / y_max)

    def x(index: int) -> float:
        if count == 1:
            return _PAD_LEFT + plot_w / 2
        return _PAD_LEFT + plot_w * index / (count - 1)

    parts = [
        f'<svg class="chart-svg" viewBox="0 0 {width} {height}" '
        'preserveAspectRatio="xMidYMid meet" aria-hidden="true">'
    ]
    for value in ticks:
        grid_y = y(value)
        parts.append(
            f'<line class="grid" x1="{_PAD_LEFT}" y1="{grid_y:.1f}" '
            f'x2="{_PAD_LEFT + plot_w}" y2="{grid_y:.1f}"/>'
        )
        parts.append(
            f'<text class="tick" x="{_PAD_LEFT - 8}" y="{grid_y + 4:.1f}" '
            f'text-anchor="end">{_fmt(value)}</text>'
        )
    for index, label in enumerate(x_labels):
        label_x = x(index)
        label_y = height - _PAD_BOTTOM + 16
        parts.append(
            f'<text class="tick" x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="end" '
            f'transform="rotate(-40 {label_x:.1f} {label_y:.1f})">{escape(label)}</text>'
        )
    for item in series:
        points = " ".join(
            f"{x(index):.1f},{y(value):.1f}" for index, value in enumerate(item.values)
        )
        parts.append(
            f'<polyline class="chart-line" points="{points}" style="stroke:{item.color}"/>'
        )
        for index, value in enumerate(item.values):
            parts.append(
                f'<circle class="chart-dot" cx="{x(index):.1f}" cy="{y(value):.1f}" r="3.2" '
                f'style="stroke:{item.color}"><title>{escape(item.label)}: {_fmt(value)}</title></circle>'
            )
    parts.append("</svg>")
    return "".join(parts)


def bar_chart(
    bars: Sequence[Bar],
    *,
    width: int = 660,
    bar_height: int = 24,
    gap: int = 8,
    label_width: int = 132,
) -> str:
    """Barras horizontais, uma por item, com o rótulo à esquerda.

    Bom para comparar jogadores num único Torneio, onde os nomes são longos.
    Devolve uma string vazia quando não há o que desenhar. Decorativo
    (``aria-hidden``): os valores estão na tabela.
    """
    if not bars:
        return ""
    top = max(bar.value for bar in bars) or 1.0
    pad = 6
    track_x = label_width + 10
    track_w = max(1, width - track_x - 40)
    height = pad * 2 + len(bars) * (bar_height + gap) - gap
    parts = [
        f'<svg class="chart-svg" viewBox="0 0 {width} {height}" '
        'preserveAspectRatio="xMidYMid meet" aria-hidden="true">'
    ]
    for index, bar in enumerate(bars):
        row_y = pad + index * (bar_height + gap)
        baseline = row_y + bar_height * 0.72
        bar_w = max(2.0, track_w * (bar.value / top))
        parts.append(
            f'<text class="tick bar-label" x="{label_width}" y="{baseline:.1f}" '
            f'text-anchor="end">{escape(bar.label)}</text>'
        )
        parts.append(
            f'<rect class="bar-track" x="{track_x}" y="{row_y}" '
            f'width="{track_w}" height="{bar_height}" rx="4"/>'
        )
        parts.append(
            f'<rect class="bar" x="{track_x}" y="{row_y}" width="{bar_w:.1f}" '
            f'height="{bar_height}" rx="4" style="fill:{bar.color}">'
            f"<title>{escape(bar.label)}: {_fmt(bar.value)}</title></rect>"
        )
        parts.append(
            f'<text class="tick bar-value" x="{track_x + track_w + 8}" '
            f'y="{baseline:.1f}">{_fmt(bar.value)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _nice_max(value: float) -> float:
    """Arredonda o topo do eixo para um número redondo (1, 2, 2.5, 5 ou 10)."""
    if value <= 0:
        return 0.0
    base = 10 ** math.floor(math.log10(value))
    for multiple in (1, 2, 2.5, 5, 10):
        if value <= multiple * base:
            return multiple * base
    return 10 * base


def _rank_ticks(top: int) -> list[int]:
    """Poucos rótulos inteiros de Posição, do 1 até ``top``."""
    if top <= 5:
        return list(range(1, top + 1))
    step = max(1, round((top - 1) / 4))
    ticks = list(range(1, top + 1, step))
    if ticks[-1] != top:
        ticks.append(top)
    return ticks


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"
