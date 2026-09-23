"""Testes do workflow de coleta e publicação — o contrato do arquivo.

Sem GitHub no ambiente, o que dá para garantir aqui é o contrato do workflow:
quando dispara, o que roda e como publica. A coleta em si é testada nos outros
módulos; o recuo em ``429`` mora no cliente do Lichess.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "coleta.yml"
TEXT = WORKFLOW.read_text(encoding="utf-8")


def test_dispara_agendado_e_por_demanda() -> None:
    assert "schedule:" in TEXT
    assert "workflow_dispatch:" in TEXT


def test_o_cron_cai_domingo_a_noite_em_sao_paulo() -> None:
    match = re.search(r'cron:\s*"([^"]+)"', TEXT)
    assert match is not None
    assert match.group(1) == "30 23 * * 0"

    # O cron é UTC: 23:30 de domingo é 20:30 em São Paulo (UTC-3).
    sunday = datetime(2026, 9, 20, 23, 30, tzinfo=timezone.utc)
    local = sunday.astimezone(ZoneInfo("America/Sao_Paulo"))
    assert (local.weekday(), local.hour, local.minute) == (6, 20, 30)


def test_coleta_gera_a_pagina_e_commita_o_arquivo() -> None:
    assert "ccc-arena collect" in TEXT
    assert "ccc-arena site" in TEXT
    assert "git add archive" in TEXT
    # Sem mudança no arquivo, não há commit vazio.
    assert "git diff --cached --quiet" in TEXT


def test_publica_a_pagina() -> None:
    assert "actions/upload-pages-artifact" in TEXT
    assert "path: site" in TEXT
    assert "actions/deploy-pages" in TEXT


def test_uma_queda_do_lichess_nao_derruba_a_pagina() -> None:
    # A coleta pode falhar sem interromper a geração e a publicação da página.
    assert "continue-on-error: true" in TEXT
