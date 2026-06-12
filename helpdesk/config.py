"""Configuração do helpdesk lida de variáveis de ambiente.

Mantém caminhos e (futuramente) segredos fora do código-fonte: o caminho do
banco SQLite e o do arquivo JSON do quadro de atendentes. Nada aqui deve conter
credenciais: valores sensíveis entram por variável de ambiente / arquivo .env
(já ignorado pelo git; os nomes esperados estão em ``.env.example``).

Também oferece um diagnóstico seguro da configuração local::

    python -m helpdesk.config check

A checagem valida caminhos e o quadro de atendentes **sem efeitos colaterais**
(não cria banco, não escreve nada) e reporta as variáveis reservadas para a
integração futura apenas como definida/não definida — **valores nunca são
exibidos**. Complementa o pré-voo do fluxo (``python -m helpdesk.demo check``);
checklist completo em ``docs/pre-integracao.md``.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# Caminho padrão do banco SQLite, relativo ao diretório de execução.
DEFAULT_DB_PATH = "helpdesk.sqlite3"

# Nome da variável de ambiente que sobrescreve o caminho do banco.
DB_PATH_ENV = "HELPDESK_DB_PATH"

# Nome da variável de ambiente com o caminho do arquivo JSON do quadro de
# atendentes. Sem ela, o sistema usa um quadro de exemplo (demo/testes).
ATTENDANTS_PATH_ENV = "HELPDESK_ATTENDANTS_PATH"

# Variáveis reservadas para a integração de mensagens (Fase 3 do roadmap).
# O código ainda não as utiliza: os nomes ficam registrados aqui (e em
# .env.example) para a checagem reportar presença/ausência. Os VALORES são
# sensíveis e nunca devem aparecer em saída de terminal, log ou commit.
INTEGRATION_ENV_VARS: tuple[str, ...] = (
    "WHATSAPP_TOKEN",
    "WHATSAPP_PHONE_NUMBER_ID",
    "WHATSAPP_VERIFY_TOKEN",
    "WHATSAPP_APP_SECRET",
)


def database_path() -> str:
    """Caminho do arquivo SQLite, configurável via ``HELPDESK_DB_PATH``."""
    return os.environ.get(DB_PATH_ENV, DEFAULT_DB_PATH)


def attendants_path() -> str | None:
    """Caminho do JSON do quadro de atendentes, ou None se não configurado."""
    return os.environ.get(ATTENDANTS_PATH_ENV) or None


# --------------------------------------------------------------------------- #
# Checagem segura da configuração local
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ConfigStep:
    """Um item da checagem de configuração: o que foi olhado e como está."""

    label: str
    ok: bool
    detail: str = ""


def _check_database() -> ConfigStep:
    """Valida o caminho do banco sem criar nem abrir arquivo algum."""
    path = Path(database_path())
    origem = (
        f"via {DB_PATH_ENV}" if os.environ.get(DB_PATH_ENV) else "padrão"
    )
    directory = path.parent  # para nome solto ("x.sqlite3"), é o diretório atual
    if not directory.is_dir():
        return ConfigStep(
            "banco SQLite",
            False,
            f"{path} ({origem}) — o diretório {directory} não existe",
        )
    if not os.access(directory, os.W_OK):
        return ConfigStep(
            "banco SQLite",
            False,
            f"{path} ({origem}) — sem permissão de escrita em {directory}",
        )
    estado = "arquivo existe" if path.exists() else "será criado no primeiro uso"
    return ConfigStep("banco SQLite", True, f"{path} ({origem}) — {estado}")


def _check_attendants() -> ConfigStep:
    """Valida o quadro de atendentes configurado (ou o exemplo embutido)."""
    # Import local para a checagem não depender do módulo na importação.
    from helpdesk.attendants import load_roster

    configured = attendants_path()
    try:
        roster = load_roster()
        ativos = sum(1 for attendant in roster if attendant.active)
    except Exception as exc:
        return ConfigStep("quadro de atendentes", False, str(exc))
    if configured:
        detail = (
            f"{configured} (via {ATTENDANTS_PATH_ENV}) — "
            f"{len(roster)} no quadro, {ativos} ativo(s)"
        )
    else:
        detail = (
            f"{ATTENDANTS_PATH_ENV} não definida — usando o quadro de exemplo "
            f"({len(roster)} no quadro, {ativos} ativo(s))"
        )
    if ativos == 0:
        return ConfigStep(
            "quadro de atendentes",
            False,
            detail + " — o rodízio precisa de ao menos um ativo",
        )
    return ConfigStep("quadro de atendentes", True, detail)


def _check_dotenv() -> ConfigStep:
    """Informa sobre o arquivo .env local (que o projeto não carrega sozinho)."""
    if Path(".env").exists():
        return ConfigStep(
            "arquivo .env",
            True,
            "presente (ignorado pelo git; lembrete: o projeto não lê o .env "
            "automaticamente — defina as variáveis no ambiente)",
        )
    return ConfigStep(
        "arquivo .env",
        True,
        "ausente (opcional; os nomes esperados estão em .env.example)",
    )


def _check_integration_vars() -> list[ConfigStep]:
    """Reporta presença/ausência das variáveis reservadas — nunca os valores."""
    steps: list[ConfigStep] = []
    for name in INTEGRATION_ENV_VARS:
        if os.environ.get(name):
            detail = "definida (valor não exibido)"
        else:
            detail = "não definida (reservada para a integração futura)"
        steps.append(ConfigStep(name, True, detail))
    return steps


def run_config_check() -> list[ConfigStep]:
    """Checagem completa da configuração local, sem efeitos colaterais.

    Nenhum passo cria arquivo, abre banco ou contata serviço externo; valores
    de variáveis sensíveis nunca entram nos resultados.
    """
    steps = [_check_database(), _check_attendants(), _check_dotenv()]
    steps.extend(_check_integration_vars())
    return steps


def _cmd_check(args: argparse.Namespace) -> None:
    print("Checagem da configuração local (somente leitura, sem segredos):\n")
    steps = run_config_check()
    for step in steps:
        marcador = "[ok]" if step.ok else "[FALHOU]"
        detalhe = f" — {step.detail}" if step.detail else ""
        print(f"  {marcador:<8} {step.label}{detalhe}")
    print()
    falhas = [step for step in steps if not step.ok]
    if falhas:
        sys.exit(
            f"{len(falhas)} item(ns) com problema. Corrija acima e rode de novo: "
            "python -m helpdesk.config check"
        )
    print(f"Configuração ok ({len(steps)} itens verificados).")
    print("Pré-voo do fluxo completo: python -m helpdesk.demo check")


def main() -> None:
    # Saída com acentos em qualquer console (mesmo ajuste do main.py); feito
    # aqui dentro para a importação do módulo não mexer no stdout de ninguém.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Configuração do helpdesk (caminhos e variáveis de ambiente)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser(
        "check",
        help="diagnóstico seguro da configuração local (não exibe valores "
        "de variáveis sensíveis)",
    )
    check.set_defaults(func=_cmd_check)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
