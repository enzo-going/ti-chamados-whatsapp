"""Configuração do helpdesk lida de variáveis de ambiente.

Mantém caminhos e (futuramente) segredos fora do código-fonte: o caminho do
banco SQLite e o do arquivo JSON do quadro de atendentes. Nada aqui deve conter
credenciais: valores sensíveis entram por variável de ambiente / arquivo .env
(já ignorado pelo git).
"""

from __future__ import annotations

import os

# Caminho padrão do banco SQLite, relativo ao diretório de execução.
DEFAULT_DB_PATH = "helpdesk.sqlite3"

# Nome da variável de ambiente que sobrescreve o caminho do banco.
DB_PATH_ENV = "HELPDESK_DB_PATH"

# Nome da variável de ambiente com o caminho do arquivo JSON do quadro de
# atendentes. Sem ela, o sistema usa um quadro de exemplo (demo/testes).
ATTENDANTS_PATH_ENV = "HELPDESK_ATTENDANTS_PATH"


def database_path() -> str:
    """Caminho do arquivo SQLite, configurável via ``HELPDESK_DB_PATH``."""
    return os.environ.get(DB_PATH_ENV, DEFAULT_DB_PATH)


def attendants_path() -> str | None:
    """Caminho do JSON do quadro de atendentes, ou None se não configurado."""
    return os.environ.get(ATTENDANTS_PATH_ENV) or None
