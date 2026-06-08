"""Camada de transporte de mensagens.

O serviço fala apenas com esta interface. Em testes e no protótipo usamos o
`FakeTransport`, que apenas guarda as respostas enviadas. Para produção, basta
implementar `MessagingTransport` com a WhatsApp Cloud API (oficial) — sem mexer
na lógica de domínio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class MessagingTransport(Protocol):
    """Contrato de envio de mensagens de volta ao funcionário."""

    def send(self, recipient: str, text: str) -> None: ...


@dataclass
class SentMessage:
    recipient: str
    text: str


@dataclass
class FakeTransport:
    """Transporte de mentira para testes/demonstração: registra os envios."""

    sent: list[SentMessage] = field(default_factory=list)

    def send(self, recipient: str, text: str) -> None:
        self.sent.append(SentMessage(recipient=recipient, text=text))

    def last_to(self, recipient: str) -> str | None:
        for msg in reversed(self.sent):
            if msg.recipient == recipient:
                return msg.text
        return None
