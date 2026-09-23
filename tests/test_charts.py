"""Testes dos gráficos em SVG — sem rede, sem JavaScript."""

from __future__ import annotations

import re

from ccc_arena_results.charts import Bar, Series, bar_chart, line_chart


def test_sem_dados_nao_gera_svg() -> None:
    assert line_chart([], x_labels=[]) == ""
    assert line_chart([Series("A", ())], x_labels=()) == ""
    assert bar_chart([]) == ""


def test_desenha_linha_e_um_ponto_por_valor() -> None:
    svg = line_chart(
        [Series("A", (10.0, 20.0, 5.0), "var(--c1)")],
        x_labels=("01/01", "08/01", "15/01"),
    )

    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")
    assert svg.count("<polyline") == 1
    assert svg.count("<circle") == 3
    assert "var(--c1)" in svg


def test_varias_series_geram_varias_linhas() -> None:
    svg = line_chart(
        [Series("A", (1.0, 2.0), "var(--c1)"), Series("B", (2.0, 1.0), "var(--c2)")],
        x_labels=("a", "b"),
    )

    assert svg.count("<polyline") == 2
    assert svg.count("<circle") == 4


def test_rotulos_sao_escapados() -> None:
    svg = line_chart([Series("A", (1.0, 2.0))], x_labels=("<b>", "&"))

    assert "<b>" not in svg
    assert "&lt;b&gt;" in svg
    assert "&amp;" in svg


def test_ponto_unico_fica_centralizado() -> None:
    svg = line_chart([Series("A", (7.0,))], x_labels=("só",))

    assert svg.count("<circle") == 1


def test_eixo_invertido_coloca_o_menor_no_topo() -> None:
    svg = line_chart([Series("A", (1.0, 5.0))], x_labels=("a", "b"), invert_y=True)
    ys = [float(value) for value in re.findall(r'<circle[^>]*cy="([\d.]+)"', svg)]

    # Posição: o 1º lugar (valor 1) fica acima do 5º (valor 5).
    assert ys[0] < ys[1]


def test_barras_uma_por_item_e_a_maior_e_mais_larga() -> None:
    svg = bar_chart([Bar("A", 10.0), Bar("B", 5.0)])

    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")
    assert svg.count('class="bar"') == 2
    assert svg.count("<title>") == 2

    widths = [float(value) for value in re.findall(r'<rect class="bar"[^>]*width="([\d.]+)"', svg)]
    assert widths[0] > widths[1]


def test_rotulo_de_barra_e_escapado() -> None:
    svg = bar_chart([Bar("<b>", 3.0)])

    assert "<b>" not in svg
    assert "&lt;b&gt;" in svg
