"""Serviço principal: orquestra triagem, criação/reabertura, atribuição e resposta.

É o coração do sistema e não conhece WhatsApp — recebe `Message`, decide o que
fazer e responde pelo `MessagingTransport`. Isso mantém a regra de negócio
testável de ponta a ponta sem nenhuma dependência externa.
"""

from __future__ import annotations

from datetime import timedelta

from helpdesk import replies, triage
from helpdesk.models import Attendant, Message, Status, Ticket
from helpdesk.repository import InMemoryTicketRepository, TicketRepository
from helpdesk.transport import MessagingTransport

# Janela em que uma nova mensagem do mesmo remetente reabre o último chamado
# fechado em vez de abrir um novo (inspirado na regra de 2h do whaticket).
DEFAULT_REOPEN_WINDOW = timedelta(hours=2)


class HelpdeskService:
    def __init__(
        self,
        transport: MessagingTransport,
        attendants: list[Attendant],
        repository: TicketRepository | None = None,
        reopen_window: timedelta = DEFAULT_REOPEN_WINDOW,
    ) -> None:
        if not attendants:
            raise ValueError("É preciso ao menos um atendente.")
        self.transport = transport
        self.attendants = attendants
        self.repository = repository or InMemoryTicketRepository()
        self.reopen_window = reopen_window
        self._round_robin = 0

    # ------------------------------------------------------------------ #
    # Fluxo principal
    # ------------------------------------------------------------------ #
    def handle_message(self, message: Message) -> Ticket:
        """Processa uma mensagem recebida e devolve o chamado afetado."""
        reopened_ticket = self._try_reopen(message)
        if reopened_ticket is not None:
            reopened_ticket.touch(f"Reaberto por nova mensagem: {message.text!r}")
            reopened_ticket.status = Status.ABERTO
            self.transport.send(message.sender, replies.reopened(reopened_ticket))
            return reopened_ticket

        ticket = self._create_ticket(message)
        self._assign(ticket)
        self.transport.send(message.sender, replies.acknowledgement(ticket))
        return ticket

    # ------------------------------------------------------------------ #
    # Operações de atendimento (usadas pelos atendentes / painel futuro)
    # ------------------------------------------------------------------ #
    def start_progress(self, ticket_id: int) -> Ticket:
        ticket = self._require(ticket_id)
        ticket.status = Status.EM_ANDAMENTO
        ticket.touch("Atendimento iniciado.")
        return ticket

    def resolve(self, ticket_id: int, note: str = "") -> Ticket:
        ticket = self._require(ticket_id)
        ticket.status = Status.RESOLVIDO
        ticket.touch(f"Resolvido. {note}".strip())
        ticket.closed_at = ticket.updated_at
        return ticket

    def close(self, ticket_id: int) -> Ticket:
        ticket = self._require(ticket_id)
        ticket.status = Status.FECHADO
        ticket.touch("Fechado.")
        ticket.closed_at = ticket.updated_at
        return ticket

    # ------------------------------------------------------------------ #
    # Internos
    # ------------------------------------------------------------------ #
    def _create_ticket(self, message: Message) -> Ticket:
        category = triage.classify_category(message.text)
        priority = triage.classify_priority(message.text)
        subject = triage.make_subject(message.text)
        ticket = Ticket(
            id=self.repository.next_id(),
            sender=message.sender,
            sender_name=message.sender_name,
            category=category,
            priority=priority,
            subject=subject,
            created_at=message.received_at,
            updated_at=message.received_at,
        )
        ticket.history.append(f"Aberto: {message.text!r}")
        self.repository.add(ticket)
        return ticket

    def _assign(self, ticket: Ticket) -> None:
        """Atribui o chamado a um atendente em rodízio (round-robin)."""
        attendant = self.attendants[self._round_robin % len(self.attendants)]
        self._round_robin += 1
        ticket.assignee = attendant
        ticket.status = Status.ATRIBUIDO
        ticket.touch(f"Atribuído a {attendant.name}.")

    def _try_reopen(self, message: Message) -> Ticket | None:
        last_closed = self.repository.last_closed_for(message.sender)
        if last_closed is None or last_closed.closed_at is None:
            return None
        if (message.received_at - last_closed.closed_at) <= self.reopen_window:
            return last_closed
        return None

    def _require(self, ticket_id: int) -> Ticket:
        ticket = self.repository.get(ticket_id)
        if ticket is None:
            raise KeyError(f"Chamado #{ticket_id} não encontrado.")
        return ticket
