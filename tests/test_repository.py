"""Testes do repositório em memória."""

import unittest
from datetime import timedelta

from helpdesk.models import Category, Priority, Status, Ticket, _now
from helpdesk.repository import InMemoryTicketRepository


def make_ticket(repo: InMemoryTicketRepository, sender: str, status: Status) -> Ticket:
    t = Ticket(
        id=repo.next_id(),
        sender=sender,
        category=Category.REDE,
        priority=Priority.MEDIA,
        subject="teste",
        status=status,
    )
    if status in (Status.RESOLVIDO, Status.FECHADO):
        t.closed_at = _now()
    repo.add(t)
    return t


class TestInMemoryRepository(unittest.TestCase):
    def test_ids_incrementais(self):
        repo = InMemoryTicketRepository()
        self.assertEqual(repo.next_id(), 1)
        self.assertEqual(repo.next_id(), 2)

    def test_list_open_ignora_fechados(self):
        repo = InMemoryTicketRepository()
        make_ticket(repo, "a", Status.ABERTO)
        make_ticket(repo, "b", Status.RESOLVIDO)
        abertos = repo.list_open()
        self.assertEqual(len(abertos), 1)
        self.assertEqual(abertos[0].sender, "a")

    def test_last_closed_for_pega_mais_recente(self):
        repo = InMemoryTicketRepository()
        antigo = make_ticket(repo, "a", Status.FECHADO)
        antigo.closed_at = _now() - timedelta(hours=3)
        recente = make_ticket(repo, "a", Status.RESOLVIDO)
        recente.closed_at = _now()
        encontrado = repo.last_closed_for("a")
        self.assertEqual(encontrado.id, recente.id)

    def test_last_closed_for_sem_fechados_retorna_none(self):
        repo = InMemoryTicketRepository()
        make_ticket(repo, "a", Status.ABERTO)
        self.assertIsNone(repo.last_closed_for("a"))


if __name__ == "__main__":
    unittest.main()
