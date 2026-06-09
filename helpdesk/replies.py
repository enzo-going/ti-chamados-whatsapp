"""Mensagens automáticas enviadas ao funcionário (pt-BR).

Centralizadas aqui para serem fáceis de revisar e ajustar ao tom do CAMPS.
"""

from __future__ import annotations

from helpdesk.models import Category, Priority, Ticket

_CATEGORY_LABEL = {
    Category.REDE: "Rede / Internet",
    Category.HARDWARE: "Hardware",
    Category.SOFTWARE: "Software / Sistemas",
    Category.ACESSO: "Acesso / Senhas",
    Category.IMPRESSORA: "Impressora",
    Category.EMPRESTIMO_EQUIPAMENTO: "Empréstimo de equipamento",
    Category.OUTROS: "Geral",
}

_PRIORITY_LABEL = {
    Priority.ALTA: "alta",
    Priority.MEDIA: "média",
    Priority.BAIXA: "baixa",
}


def acknowledgement(ticket: Ticket) -> str:
    """Confirma a abertura do chamado para o funcionário."""
    categoria = _CATEGORY_LABEL[ticket.category]
    prioridade = _PRIORITY_LABEL[ticket.priority]
    return (
        f"✅ Recebemos seu chamado *#{ticket.id}*.\n"
        f"Categoria: {categoria}\n"
        f"Prioridade: {prioridade}\n\n"
        "A equipe de TI foi notificada e vai te atender o quanto antes. "
        "Pode responder por aqui se quiser acrescentar detalhes."
    )


def reopened(ticket: Ticket) -> str:
    """Avisa que a mensagem reabriu um chamado recente."""
    return (
        f"🔁 Reabrimos seu chamado *#{ticket.id}* com a nova mensagem. "
        "A equipe de TI já foi avisada."
    )


def followup(ticket: Ticket) -> str:
    """Confirma que a mensagem foi anexada a um chamado já aberto."""
    return (
        f"📝 Anotamos a informação no seu chamado *#{ticket.id}*, que segue em "
        "atendimento. Não abrimos um novo chamado."
    )


def assigned(ticket: Ticket) -> str:
    """Avisa quem vai atender (opcional, usado quando há atribuição imediata)."""
    nome = ticket.assignee.name if ticket.assignee else "a equipe"
    return f"👤 Seu chamado *#{ticket.id}* está com {nome}."
