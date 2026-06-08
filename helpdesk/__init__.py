"""Núcleo de um helpdesk de TI integrável a um WhatsApp compartilhado.

O pacote é agnóstico de transporte: a lógica de triagem, criação de chamados
e atribuição a atendentes não depende de nenhuma biblioteca de WhatsApp.
Um transporte real (Cloud API, etc.) pode ser plugado depois pela interface
em `helpdesk.transport`.
"""

from helpdesk.models import (
    Attendant,
    Category,
    Message,
    Priority,
    Status,
    Ticket,
)
from helpdesk.service import HelpdeskService

__all__ = [
    "Attendant",
    "Category",
    "Message",
    "Priority",
    "Status",
    "Ticket",
    "HelpdeskService",
]
