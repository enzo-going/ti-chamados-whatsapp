"""Serviço principal: orquestra triagem, criação/reabertura, atribuição e resposta.

É o coração do sistema e não conhece WhatsApp — recebe `Message`, decide o que
fazer e responde pelo `MessagingTransport`. Isso mantém a regra de negócio
testável de ponta a ponta sem nenhuma dependência externa.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import Enum

from helpdesk import replies, triage
from helpdesk.models import Attendant, Message, ServiceMode, Status, Ticket
from helpdesk.repository import InMemoryTicketRepository, TicketRepository
from helpdesk.transport import MessagingTransport

# Janela em que uma nova mensagem do mesmo remetente reabre o último chamado
# fechado em vez de abrir um novo (inspirado na regra de 2h do whaticket).
DEFAULT_REOPEN_WINDOW = timedelta(hours=2)


class MessageOutcome(str, Enum):
    """O que uma mensagem recebida provocou no fluxo.

    Existe para que a borda (log do servidor, CLI da demo) relate **o que
    aconteceu de fato** — em vez de tratar todo evento como "novo".
    """

    CRIADO = "criado"      # abriu um chamado novo
    FOLLOWUP = "followup"  # anexada a um chamado aberto, sem abrir outro
    REABERTO = "reaberto"  # reabriu um chamado fechado recente


@dataclass(frozen=True)
class HandleResult:
    """Chamado afetado + o desfecho do processamento da mensagem."""

    ticket: Ticket
    outcome: MessageOutcome


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
        # O quadro completo fica em `attendants`; o rodízio usa só os ativos.
        # O quadro é fixo por instância: mudanças (ex.: inativar alguém) são
        # aplicadas recarregando o arquivo e recriando o serviço.
        self._active_attendants = [a for a in attendants if a.active]
        if not self._active_attendants:
            raise ValueError("É preciso ao menos um atendente ativo.")
        self.repository = repository or InMemoryTicketRepository()
        self.reopen_window = reopen_window
        self._round_robin = 0

    # ------------------------------------------------------------------ #
    # Fluxo principal
    # ------------------------------------------------------------------ #
    def handle_message(self, message: Message) -> Ticket:
        """Processa uma mensagem e devolve só o chamado afetado.

        Atalho de ``process_message`` para quem não precisa do desfecho.
        """
        return self.process_message(message).ticket

    def process_message(self, message: Message) -> HandleResult:
        """Processa uma mensagem e devolve o chamado **e o desfecho**.

        O desfecho (``MessageOutcome``) diz qual caminho a mensagem tomou — novo
        chamado, follow-up em chamado aberto ou reabertura de um fechado — para
        que o log e a CLI possam relatar com fidelidade.
        """
        followup_ticket = self._try_followup(message)
        if followup_ticket is not None:
            followup_ticket.touch(f"Mensagem adicional: {message.text!r}")
            self.repository.update(followup_ticket)
            self.transport.send(message.sender, replies.followup(followup_ticket))
            return HandleResult(followup_ticket, MessageOutcome.FOLLOWUP)

        reopened_ticket = self._try_reopen(message)
        if reopened_ticket is not None:
            reopened_ticket.touch(f"Reaberto por nova mensagem: {message.text!r}")
            reopened_ticket.status = Status.ABERTO
            self.repository.update(reopened_ticket)
            self.transport.send(message.sender, replies.reopened(reopened_ticket))
            return HandleResult(reopened_ticket, MessageOutcome.REABERTO)

        ticket = self._create_ticket(message)
        self._assign(ticket)
        self.repository.update(ticket)
        self.transport.send(message.sender, replies.acknowledgement(ticket))
        return HandleResult(ticket, MessageOutcome.CRIADO)

    # ------------------------------------------------------------------ #
    # Operações de atendimento (usadas pelos atendentes / painel futuro)
    # ------------------------------------------------------------------ #
    def start_progress(self, ticket_id: int) -> Ticket:
        ticket = self._require(ticket_id)
        ticket.status = Status.EM_ANDAMENTO
        ticket.touch("Atendimento iniciado.")
        self.repository.update(ticket)
        return ticket

    def resolve(self, ticket_id: int, note: str = "") -> Ticket:
        ticket = self._require(ticket_id)
        ticket.status = Status.RESOLVIDO
        ticket.touch(f"Resolvido. {note}".strip())
        ticket.closed_at = ticket.updated_at
        self.repository.update(ticket)
        return ticket

    def close(self, ticket_id: int) -> Ticket:
        ticket = self._require(ticket_id)
        ticket.status = Status.FECHADO
        ticket.touch("Fechado.")
        ticket.closed_at = ticket.updated_at
        self.repository.update(ticket)
        return ticket

    def set_attendance(
        self,
        ticket_id: int,
        *,
        mode: ServiceMode | None = None,
        location: str | None = None,
    ) -> Ticket:
        """Define o **local/modo de atendimento** do chamado.

        Pensado para ser acionado por um atendente (interface da Fase 4), não
        pela mensagem do funcionário. ``mode`` diz se o atendimento é presencial
        ou remoto; ``location`` é texto livre (sala, setor, evento) e costuma
        acompanhar o presencial. Atualiza só o que for informado, registra a
        mudança no histórico e persiste. Não altera status nem responsável.
        """
        if mode is None and location is None:
            raise ValueError("Informe ao menos 'mode' ou 'location'.")
        ticket = self._require(ticket_id)
        if mode is not None:
            ticket.service_mode = mode
        if location is not None:
            ticket.location = location

        if ticket.service_mode is ServiceMode.REMOTO:
            nota = "Atendimento definido como remoto."
        elif ticket.service_mode is ServiceMode.PRESENCIAL:
            onde = f" em {ticket.location}" if ticket.location else ""
            nota = f"Atendimento presencial{onde}."
        else:
            nota = f"Local de atendimento: {ticket.location}."
        ticket.touch(nota)
        self.repository.update(ticket)
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
        """Atribui o chamado a um atendente **ativo**, em rodízio (round-robin).

        Inativos não recebem novas atribuições; chamados já atribuídos a quem
        saiu do quadro não são alterados (o chamado guarda o próprio responsável).
        """
        active = self._active_attendants
        attendant = active[self._round_robin % len(active)]
        self._round_robin += 1
        ticket.assignee = attendant
        ticket.status = Status.ATRIBUIDO
        ticket.touch(f"Atribuído a {attendant.name}.")

    def _try_followup(self, message: Message) -> Ticket | None:
        """Chamado aberto recente do mesmo remetente, para anexar a mensagem.

        Evita abrir um chamado novo quando a pessoa continua escrevendo sobre o
        mesmo problema. Usa a mesma janela de continuidade da reabertura,
        comparando com a última atividade do chamado (`updated_at`).
        """
        open_ticket = self.repository.last_open_for(message.sender)
        if open_ticket is None:
            return None
        if (message.received_at - open_ticket.updated_at) <= self.reopen_window:
            return open_ticket
        return None

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
