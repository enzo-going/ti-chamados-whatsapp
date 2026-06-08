"""Configuração do helpdesk lida de variáveis de ambiente.

Mantém caminhos e (futuramente) segredos fora do código-fonte. Por enquanto só
o caminho do banco SQLite. Nada aqui deve conter credenciais: valores sensíveis
entram por variável de ambiente / arquivo .env (já ignorado pelo git).
"""

from __future__ import annotations

import os

# Caminho padrão do banco SQLite, relativo ao diretório de execução.
DEFAULT_DB_PATH = "helpdesk.sqlite3"

# Nome da variável de ambiente que sobrescreve o caminho do banco.
DB_PATH_ENV = "HELPDESK_DB_PATH"


def database_path() -> str:
    """Caminho do arquivo SQLite, configurável via ``HELPDESK_DB_PATH``."""
    return os.environ.get(DB_PATH_ENV, DEFAULT_DB_PATH)
