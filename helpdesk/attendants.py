"""Quadro de atendentes configurável (arquivo JSON local).

A equipe do setor tem rotatividade, então o quadro não fica fixado no código:
é lido de um arquivo JSON apontado por ``HELPDESK_ATTENDANTS_PATH`` (ou por um
caminho passado explicitamente). Sem essa configuração, um quadro de exemplo
com papéis genéricos é usado — suficiente para demo e testes.

Formato do arquivo (lista de objetos)::

    [
        {"id": "ti1", "name": "Atendente 1", "role": "supervisor"},
        {"id": "ti2", "name": "Atendente 2", "active": false}
    ]

``role`` (padrão ``"atendente"``) e ``active`` (padrão ``true``) são opcionais.
O arquivo real é local e **não** deve ser versionado em repositório público
(pode conter nomes reais) — ``atendentes.json`` já está no ``.gitignore``;
``atendentes.exemplo.json`` mostra o formato com dados genéricos.
"""

from __future__ import annotations

import json

from helpdesk import config
from helpdesk.models import DEFAULT_ROLE, Attendant

# Campos aceitos por entrada do arquivo. Campo desconhecido é erro, não
# silêncio: um typo como "ativo" em vez de "active" deixaria alguém no rodízio
# sem querer.
_REQUIRED_FIELDS = {"id", "name"}
_OPTIONAL_FIELDS = {"role", "active"}


class InvalidRoster(ValueError):
    """O conteúdo do quadro de atendentes é inválido."""


def parse_roster(data: object) -> list[Attendant]:
    """Valida e converte o JSON já carregado em uma lista de ``Attendant``.

    O quadro completo é devolvido (inclusive inativos); quem filtra os ativos
    para o rodízio é o serviço.
    """
    if not isinstance(data, list):
        raise InvalidRoster("o quadro deve ser uma lista JSON de atendentes")
    if not data:
        raise InvalidRoster("o quadro de atendentes está vazio")
    attendants: list[Attendant] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(data):
        attendant = _parse_entry(index, item)
        if attendant.id in seen_ids:
            raise InvalidRoster(f"id duplicado no quadro: {attendant.id!r}")
        seen_ids.add(attendant.id)
        attendants.append(attendant)
    return attendants


def _parse_entry(index: int, item: object) -> Attendant:
    where = f"atendente #{index + 1}"
    if not isinstance(item, dict):
        raise InvalidRoster(f"{where}: cada entrada deve ser um objeto JSON")
    unknown = set(item) - _REQUIRED_FIELDS - _OPTIONAL_FIELDS
    if unknown:
        raise InvalidRoster(f"{where}: campos desconhecidos: {sorted(unknown)}")
    missing = _REQUIRED_FIELDS - set(item)
    if missing:
        raise InvalidRoster(f"{where}: campos obrigatórios ausentes: {sorted(missing)}")
    ident = item["id"]
    name = item["name"]
    if not isinstance(ident, str) or not ident.strip():
        raise InvalidRoster(f"{where}: 'id' deve ser texto não vazio")
    if not isinstance(name, str) or not name.strip():
        raise InvalidRoster(f"{where}: 'name' deve ser texto não vazio")
    role = item.get("role", DEFAULT_ROLE)
    if not isinstance(role, str) or not role.strip():
        raise InvalidRoster(f"{where}: 'role' deve ser texto não vazio")
    active = item.get("active", True)
    if not isinstance(active, bool):
        raise InvalidRoster(f"{where}: 'active' deve ser true ou false")
    return Attendant(
        id=ident.strip(), name=name.strip(), role=role.strip(), active=active
    )


def load_roster_file(path: str) -> list[Attendant]:
    """Carrega e valida o quadro a partir de um arquivo JSON (UTF-8)."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise InvalidRoster(f"JSON inválido em {path}: {exc}") from exc
    return parse_roster(data)


def _fallback_roster() -> list[Attendant]:
    """Quadro de exemplo com papéis genéricos (demo/testes; sem nomes reais)."""
    return [
        Attendant("ti1", "Atendente 1", role="supervisor"),
        Attendant("ti2", "Atendente 2", role="efetivo"),
        Attendant("ti3", "Atendente 3", role="efetivo"),
        Attendant("ti4", "Atendente 4", role="estagiario"),
    ]


def load_roster(path: str | None = None) -> list[Attendant]:
    """Quadro de atendentes: ``path`` explícito > variável de ambiente > exemplo.

    Com um caminho configurado (argumento ou ``HELPDESK_ATTENDANTS_PATH``), o
    arquivo é obrigatório: erro de leitura ou validação interrompe a
    inicialização em vez de cair silenciosamente no quadro de exemplo.
    """
    effective = path or config.attendants_path()
    if effective:
        return load_roster_file(effective)
    return _fallback_roster()
