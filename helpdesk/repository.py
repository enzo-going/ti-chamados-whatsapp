"""Persistência dos chamados.

Por enquanto há uma implementação em memória, suficiente para os testes e para
o protótipo. A interface (Protocol) permite trocar por SQLite/SQLAlchemy depois
sem afetar o serviço — espelhando a stack que já uso nos outros projetos.
"""

from __future__ import annotations

from typing import Protocol

from helpdesk.models import Status, Ticket


class TicketRepository(Protocol):
    """Contrato de armazenamento de chamados."""

    def add(self, ticket: Ticket) -> None: ...

    def update(self, ticket: Ticket) -> None: ...

    def next_id(self) -> int: ...

    def get(self, ticket_id: int) -> Ticket | None: ...

    def list_open(self) -> list[Ticket]: ...

    def all(self) -> list[Ticket]: ...

    def last_closed_for(self, sender: str) -> Ticket | None: ...


class InMemoryTicketRepository:
    """Implementação simples em memória (dict por id)."""

    def __init__(self) -> None:
        self._tickets: dict[int, Ticket] = {}
        self._seq = 0

    def add(self, ticket: Ticket) -> None:
        self._tickets[ticket.id] = ticket

    def update(self, ticket: Ticket) -> None:
        # Em memória os chamados são guardados por referência, então a mutação
        # já é visível; regravamos o objeto para manter o mesmo contrato das
        # implementações persistentes (ex.: SQLite), onde update() é obrigatório.
        self._tickets[ticket.id] = ticket

    def next_id(self) -> int:
        self._seq += 1
        return self._seq

    def get(self, ticket_id: int) -> Ticket | None:
        return self._tickets.get(ticket_id)

    def list_open(self) -> list[Ticket]:
        return [t for t in self._tickets.values() if t.is_open]

    def all(self) -> list[Ticket]:
        return list(self._tickets.values())

    def last_closed_for(self, sender: str) -> Ticket | None:
        """Chamado resolvido/fechado mais recente do remetente (ou None).

        A decisão de reabrir (janela de tempo) fica no serviço, que compara o
        horário da nova mensagem com `closed_at`.
        """
        closed = [
            t
            for t in self._tickets.values()
            if t.sender == sender
            and t.status in (Status.RESOLVIDO, Status.FECHADO)
            and t.closed_at is not None
        ]
        if not closed:
            return None
        return max(closed, key=lambda t: t.closed_at)  # type: ignore[arg-type]
