"""Persistência dos chamados.

Há duas implementações do mesmo contrato (``TicketRepository``):

- ``InMemoryTicketRepository``: simples, usada em testes e na demonstração.
- ``SqliteTicketRepository``: persistente em arquivo, para o MVP — sobrevive a
  reinícios sem perder chamados.

Como o serviço fala apenas com o ``Protocol``, trocar uma pela outra não exige
nenhuma alteração na regra de negócio.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Protocol

from helpdesk.models import Attendant, Category, Priority, Status, Ticket


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


# --------------------------------------------------------------------------- #
# Implementação SQLite
# --------------------------------------------------------------------------- #

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id            INTEGER PRIMARY KEY,
    sender        TEXT    NOT NULL,
    sender_name   TEXT,
    category      TEXT    NOT NULL,
    priority      TEXT    NOT NULL,
    subject       TEXT    NOT NULL,
    status        TEXT    NOT NULL,
    assignee_id   TEXT,
    assignee_name TEXT,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL,
    closed_at     TEXT,
    history       TEXT    NOT NULL DEFAULT '[]'
);
"""

# Status considerados "fechados" para fins de reabertura/listagem.
_CLOSED_STATUSES = (Status.RESOLVIDO.value, Status.FECHADO.value)


def _dt_to_iso(value: datetime | None) -> str | None:
    """Serializa um datetime (com timezone) em texto ISO 8601, ou None."""
    return value.isoformat() if value is not None else None


def _iso_to_dt(value: str | None) -> datetime | None:
    """Reconstrói um datetime a partir do texto ISO 8601, ou None."""
    return datetime.fromisoformat(value) if value is not None else None


def _row_to_ticket(row: sqlite3.Row) -> Ticket:
    """Reconstrói um ``Ticket`` a partir de uma linha do banco."""
    assignee = None
    if row["assignee_id"] is not None:
        assignee = Attendant(id=row["assignee_id"], name=row["assignee_name"])
    return Ticket(
        id=row["id"],
        sender=row["sender"],
        sender_name=row["sender_name"],
        category=Category(row["category"]),
        priority=Priority(row["priority"]),
        subject=row["subject"],
        status=Status(row["status"]),
        assignee=assignee,
        created_at=_iso_to_dt(row["created_at"]),
        updated_at=_iso_to_dt(row["updated_at"]),
        closed_at=_iso_to_dt(row["closed_at"]),
        history=json.loads(row["history"]),
    )


class SqliteTicketRepository:
    """Armazenamento de chamados em SQLite (arquivo ou ``:memory:``).

    Sobrevive a reinícios do processo: chamados, IDs e histórico ficam no banco.
    Cada ``add``/``update`` confirma a transação imediatamente (commit), o que é
    adequado ao volume de um helpdesk interno e simples de raciocinar.
    """

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    # -- escrita ------------------------------------------------------------ #
    def add(self, ticket: Ticket) -> None:
        self._conn.execute(
            """
            INSERT INTO tickets (
                id, sender, sender_name, category, priority, subject, status,
                assignee_id, assignee_name, created_at, updated_at, closed_at, history
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ticket.id, *self._values(ticket)),
        )
        self._conn.commit()

    def update(self, ticket: Ticket) -> None:
        self._conn.execute(
            """
            UPDATE tickets SET
                sender = ?, sender_name = ?, category = ?, priority = ?,
                subject = ?, status = ?, assignee_id = ?, assignee_name = ?,
                created_at = ?, updated_at = ?, closed_at = ?, history = ?
            WHERE id = ?
            """,
            (*self._values(ticket), ticket.id),
        )
        self._conn.commit()

    # -- leitura ------------------------------------------------------------ #
    def next_id(self) -> int:
        """Próximo id disponível (maior id existente + 1).

        Diferente do repositório em memória, não consome o id até que o chamado
        seja inserido — o serviço sempre chama ``next_id()`` seguido de ``add()``.
        """
        row = self._conn.execute(
            "SELECT COALESCE(MAX(id), 0) + 1 AS next FROM tickets"
        ).fetchone()
        return int(row["next"])

    def get(self, ticket_id: int) -> Ticket | None:
        row = self._conn.execute(
            "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
        ).fetchone()
        return _row_to_ticket(row) if row is not None else None

    def list_open(self) -> list[Ticket]:
        rows = self._conn.execute(
            "SELECT * FROM tickets WHERE status NOT IN (?, ?) ORDER BY id",
            _CLOSED_STATUSES,
        ).fetchall()
        return [_row_to_ticket(r) for r in rows]

    def all(self) -> list[Ticket]:
        rows = self._conn.execute("SELECT * FROM tickets ORDER BY id").fetchall()
        return [_row_to_ticket(r) for r in rows]

    def last_closed_for(self, sender: str) -> Ticket | None:
        """Chamado resolvido/fechado mais recente do remetente (ou None).

        Os timestamps são gravados em ISO 8601 UTC, cuja ordem lexicográfica
        coincide com a cronológica — por isso ``ORDER BY closed_at`` basta.
        """
        row = self._conn.execute(
            """
            SELECT * FROM tickets
            WHERE sender = ? AND status IN (?, ?) AND closed_at IS NOT NULL
            ORDER BY closed_at DESC
            LIMIT 1
            """,
            (sender, *_CLOSED_STATUSES),
        ).fetchone()
        return _row_to_ticket(row) if row is not None else None

    # -- ciclo de vida da conexão ------------------------------------------ #
    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "SqliteTicketRepository":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- internos ----------------------------------------------------------- #
    @staticmethod
    def _values(ticket: Ticket) -> tuple[object, ...]:
        """Colunas (exceto id) na ordem usada por add()/update()."""
        assignee_id = ticket.assignee.id if ticket.assignee else None
        assignee_name = ticket.assignee.name if ticket.assignee else None
        return (
            ticket.sender,
            ticket.sender_name,
            ticket.category.value,
            ticket.priority.value,
            ticket.subject,
            ticket.status.value,
            assignee_id,
            assignee_name,
            _dt_to_iso(ticket.created_at),
            _dt_to_iso(ticket.updated_at),
            _dt_to_iso(ticket.closed_at),
            json.dumps(ticket.history),
        )
