"""Camada de entrada: transforma eventos externos (payloads) em chamados.

É **local e testável** e não conhece nenhuma plataforma de mensageria específica.
Um adaptador externo (HTTP, fila, etc.) entrega um payload neutro; aqui ele é
validado, convertido em ``Message`` e processado pelo ``HelpdeskService`` — com
**idempotência**: o mesmo evento entregue mais de uma vez não duplica o chamado.

Formato do payload (JSON neutro)::

    {
        "event_id": "evt-001",                     # obrigatório: id único do evento
        "sender": "5513990000001",                 # obrigatório: identificador do remetente
        "text": "preciso de um notebook",          # obrigatório: corpo da mensagem
        "sender_name": "Funcionário X",            # opcional
        "timestamp": "2026-06-09T12:00:00+00:00"   # opcional (ISO 8601)
    }
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from helpdesk.models import Message, Ticket
from helpdesk.service import HelpdeskService


class InvalidPayload(ValueError):
    """Payload de entrada malformado ou com campos obrigatórios ausentes."""


@dataclass
class InboundEvent:
    """Evento de entrada já validado: id único + mensagem pronta para o serviço."""

    event_id: str
    message: Message


@dataclass
class IngestResult:
    """Resultado de processar um evento. ``duplicate`` indica reentrega."""

    ticket: Ticket
    duplicate: bool


def parse_payload(payload: Mapping[str, object]) -> InboundEvent:
    """Valida o payload e o converte em ``InboundEvent`` (ou levanta InvalidPayload)."""
    if not isinstance(payload, Mapping):
        raise InvalidPayload("payload deve ser um objeto JSON")
    event_id = _required_str(payload, "event_id")
    sender = _required_str(payload, "sender")
    text = _required_str(payload, "text")

    sender_name = payload.get("sender_name")
    if sender_name is not None and not isinstance(sender_name, str):
        raise InvalidPayload("sender_name deve ser texto")

    received_at = _parse_timestamp(payload.get("timestamp"))
    kwargs: dict[str, object] = {"sender": sender, "text": text, "sender_name": sender_name}
    if received_at is not None:
        kwargs["received_at"] = received_at
    return InboundEvent(event_id=event_id, message=Message(**kwargs))  # type: ignore[arg-type]


def _required_str(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidPayload(f"campo obrigatório ausente ou vazio: {key!r}")
    return value


def _parse_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidPayload("timestamp deve ser texto ISO 8601")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise InvalidPayload(f"timestamp inválido: {value!r}") from exc
    # Normaliza para UTC. Um timestamp sem fuso ("naive") é assumido como UTC:
    # todos os horários internos são aware/UTC (ver models._now), e misturar com
    # um naive quebraria o cálculo de "tempo aberto" no painel e a janela de
    # follow-up/reabertura ("can't subtract offset-naive and offset-aware").
    # UTC é o padrão de toda a base e o que o webhook da Cloud API entrega.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class MessageGateway:
    """Encaminha payloads de entrada ao serviço, garantindo idempotência.

    A idempotência usa o ``event_id``: se o evento já foi processado, devolve o
    chamado existente sem criar outro. O registro de eventos vive no repositório
    (persistente no SQLite), então sobrevive a reinícios do processo.
    """

    def __init__(self, service: HelpdeskService) -> None:
        self._service = service

    def ingest(self, payload: Mapping[str, object]) -> IngestResult:
        event = parse_payload(payload)
        repo = self._service.repository

        existing_id = repo.seen_event(event.event_id)
        if existing_id is not None:
            ticket = repo.get(existing_id)
            if ticket is not None:
                return IngestResult(ticket=ticket, duplicate=True)

        ticket = self._service.handle_message(event.message)
        repo.record_event(event.event_id, ticket.id)
        return IngestResult(ticket=ticket, duplicate=False)
