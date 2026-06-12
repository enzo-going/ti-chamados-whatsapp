"""Testes do repositório SQLite.

Cobrem três frentes:
1. O mesmo contrato do repositório em memória (ids, listagens, último fechado).
2. Persistência real: o que foi gravado sobrevive ao fechar e reabrir o banco.
3. Integração com o HelpdeskService usando SQLite de ponta a ponta.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from helpdesk.models import Attendant, Category, Message, Priority, Status, Ticket, _now
from helpdesk.repository import SqliteTicketRepository
from helpdesk.service import HelpdeskService
from helpdesk.transport import FakeTransport


def make_ticket(repo: SqliteTicketRepository, sender: str, status: Status) -> Ticket:
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


class SqliteRepoTestCase(unittest.TestCase):
    """Cria um banco em arquivo temporário para cada teste."""

    def setUp(self) -> None:
        self._dir = tempfile.mkdtemp()
        self.db_path = str(Path(self._dir) / "test.sqlite3")
        self.repo = SqliteTicketRepository(self.db_path)

    def tearDown(self) -> None:
        self.repo.close()
        shutil.rmtree(self._dir, ignore_errors=True)


class TestContract(SqliteRepoTestCase):
    def test_next_id_reflete_maior_id(self):
        self.assertEqual(self.repo.next_id(), 1)
        make_ticket(self.repo, "a", Status.ABERTO)
        self.assertEqual(self.repo.next_id(), 2)
        make_ticket(self.repo, "b", Status.ABERTO)
        self.assertEqual(self.repo.next_id(), 3)

    def test_get_inexistente_retorna_none(self):
        self.assertIsNone(self.repo.get(999))

    def test_add_e_get(self):
        t = make_ticket(self.repo, "a", Status.ABERTO)
        encontrado = self.repo.get(t.id)
        self.assertIsNotNone(encontrado)
        self.assertEqual(encontrado.sender, "a")

    def test_list_open_ignora_fechados(self):
        make_ticket(self.repo, "a", Status.ABERTO)
        make_ticket(self.repo, "b", Status.RESOLVIDO)
        make_ticket(self.repo, "c", Status.FECHADO)
        abertos = self.repo.list_open()
        self.assertEqual(len(abertos), 1)
        self.assertEqual(abertos[0].sender, "a")

    def test_last_closed_for_pega_mais_recente(self):
        antigo = make_ticket(self.repo, "a", Status.FECHADO)
        antigo.closed_at = _now() - timedelta(hours=3)
        self.repo.update(antigo)
        recente = make_ticket(self.repo, "a", Status.RESOLVIDO)
        recente.closed_at = _now()
        self.repo.update(recente)
        encontrado = self.repo.last_closed_for("a")
        self.assertEqual(encontrado.id, recente.id)

    def test_last_closed_for_sem_fechados_retorna_none(self):
        make_ticket(self.repo, "a", Status.ABERTO)
        self.assertIsNone(self.repo.last_closed_for("a"))

    def test_last_open_for_ignora_fechados(self):
        self.assertIsNone(self.repo.last_open_for("a"))
        aberto = make_ticket(self.repo, "a", Status.ATRIBUIDO)
        make_ticket(self.repo, "a", Status.RESOLVIDO)  # fechado, deve ser ignorado
        encontrado = self.repo.last_open_for("a")
        self.assertIsNotNone(encontrado)
        self.assertEqual(encontrado.id, aberto.id)

    def test_update_persiste_mudancas(self):
        t = make_ticket(self.repo, "a", Status.ABERTO)
        t.status = Status.EM_ANDAMENTO
        t.assignee = Attendant("ti1", "Atendente 1")
        t.touch("nota nova")
        self.repo.update(t)
        recarregado = self.repo.get(t.id)
        self.assertEqual(recarregado.status, Status.EM_ANDAMENTO)
        self.assertEqual(recarregado.assignee, Attendant("ti1", "Atendente 1"))
        self.assertIn("nota nova", recarregado.history)

    def test_schema_version_carimbada(self):
        self.assertEqual(self.repo.schema_version(), 2)

    def test_eventos_processados(self):
        self.assertIsNone(self.repo.seen_event("e1"))
        t = make_ticket(self.repo, "a", Status.ABERTO)
        self.repo.record_event("e1", t.id)
        self.assertEqual(self.repo.seen_event("e1"), t.id)
        # Regravar o mesmo evento é idempotente (não falha nem altera).
        self.repo.record_event("e1", t.id)
        self.assertEqual(self.repo.seen_event("e1"), t.id)


class TestPersistencia(SqliteRepoTestCase):
    def test_sobrevive_reabertura_do_banco(self):
        t = Ticket(
            id=self.repo.next_id(),
            sender="5513999",
            sender_name="Funcionário X",
            category=Category.REDE,
            priority=Priority.ALTA,
            subject="rede caiu",
            status=Status.ATRIBUIDO,
            assignee=Attendant("ti1", "Atendente 1"),
        )
        t.touch("Aberto")
        self.repo.add(t)
        self.repo.update(t)
        self.repo.close()

        # Reabre o mesmo arquivo num repositório novo.
        repo2 = SqliteTicketRepository(self.db_path)
        try:
            recarregado = repo2.get(t.id)
            self.assertIsNotNone(recarregado)
            self.assertEqual(recarregado.sender, "5513999")
            self.assertEqual(recarregado.sender_name, "Funcionário X")
            self.assertEqual(recarregado.category, Category.REDE)
            self.assertEqual(recarregado.priority, Priority.ALTA)
            self.assertEqual(recarregado.status, Status.ATRIBUIDO)
            self.assertEqual(recarregado.assignee, Attendant("ti1", "Atendente 1"))
            self.assertIn("Aberto", recarregado.history)
        finally:
            repo2.close()

    def test_round_trip_preserva_datetime_com_timezone(self):
        t = make_ticket(self.repo, "a", Status.RESOLVIDO)
        original = t.closed_at
        recarregado = self.repo.get(t.id)
        self.assertEqual(recarregado.closed_at, original)
        self.assertIsNotNone(recarregado.closed_at.tzinfo)


class TestClear(SqliteRepoTestCase):
    def test_clear_esvazia_e_reinicia_ids(self):
        make_ticket(self.repo, "a", Status.ABERTO)
        t2 = make_ticket(self.repo, "b", Status.ABERTO)
        self.repo.record_event("e1", t2.id)
        self.assertEqual(len(self.repo.all()), 2)

        self.repo.clear()

        self.assertEqual(self.repo.all(), [])
        self.assertEqual(self.repo.next_id(), 1)  # ids recomeçam do 1
        self.assertIsNone(self.repo.seen_event("e1"))

    def test_clear_funciona_com_arquivo_aberto_por_outra_conexao(self):
        # Regressão (Windows/WinError 32): o --reset não pode depender de apagar
        # o arquivo, que falha enquanto outro processo (o servidor da demo) o
        # mantém aberto. Limpar via SQL por uma 2ª conexão deve funcionar e ficar
        # visível para a 1ª.
        servidor = SqliteTicketRepository(self.db_path, allow_cross_thread=True)
        try:
            make_ticket(servidor, "a", Status.ABERTO)
            self.assertEqual(len(servidor.all()), 1)

            recriador = SqliteTicketRepository(self.db_path)  # 2ª conexão (o _cmd_seed)
            try:
                recriador.clear()
            finally:
                recriador.close()

            self.assertEqual(servidor.all(), [])  # 1ª conexão enxerga a limpeza
        finally:
            servidor.close()


class TestIntegracaoServico(SqliteRepoTestCase):
    def _service(self) -> tuple[HelpdeskService, FakeTransport]:
        transport = FakeTransport()
        attendants = [Attendant("ti1", "Atendente 1"), Attendant("ti2", "Atendente 2")]
        service = HelpdeskService(
            transport=transport, attendants=attendants, repository=self.repo
        )
        return service, transport

    def test_cria_e_persiste_via_servico(self):
        service, _ = self._service()
        ticket = service.handle_message(
            Message(sender="5513999", text="a rede caiu, ninguem consegue acessar")
        )
        # Lê do banco (não do objeto em memória) para provar a persistência.
        do_banco = self.repo.get(ticket.id)
        self.assertEqual(do_banco.category, Category.REDE)
        self.assertEqual(do_banco.priority, Priority.ALTA)
        self.assertEqual(do_banco.status, Status.ATRIBUIDO)
        self.assertIsNotNone(do_banco.assignee)

    def test_resolve_persiste_status(self):
        service, _ = self._service()
        t = service.handle_message(Message(sender="x", text="sistema lento"))
        service.resolve(t.id, "limpei temporarios")
        do_banco = self.repo.get(t.id)
        self.assertEqual(do_banco.status, Status.RESOLVIDO)
        self.assertIsNotNone(do_banco.closed_at)

    def test_reabre_dentro_da_janela_com_sqlite(self):
        service, transport = self._service()
        t = service.handle_message(Message(sender="5513999", text="rede caiu"))
        service.resolve(t.id, "reiniciei o switch")
        recarregado = self.repo.get(t.id)

        nova = Message(
            sender="5513999",
            text="voltou a cair",
            received_at=recarregado.closed_at + timedelta(minutes=30),
        )
        resultado = service.handle_message(nova)
        self.assertEqual(resultado.id, t.id)
        self.assertEqual(self.repo.get(t.id).status, Status.ABERTO)
        self.assertIn("Reabrimos", transport.last_to("5513999"))


if __name__ == "__main__":
    unittest.main()
