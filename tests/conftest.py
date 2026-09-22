"""Configuração comum dos testes.

Garante que os módulos de apoio em ``tests/`` (como ``lichess_fixtures``)
sejam importáveis sem que ``tests`` precise virar um pacote.
"""

from __future__ import annotations

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
