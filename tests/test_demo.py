"""Testes do modo de demonstração local (seed de dados fake + envio simulado)."""

from __future__ import annotations

import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from helpdesk.dashboard import render_dashboard
from helpdesk.demo import seed_demo, send_message
from helpdesk.http_app import make_server
from helpdesk.inbound import MessageGateway
from helpdesk.models import Attendant, Priority
from helpdesk.repository import InMemoryTicketRepository, SqliteTicketRepository
from helpdesk.service import HelpdeskService
from helpdesk.transport import FakeTransport


class TestSeedDemo(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryTicketRepository()
        self.now = datetime.now(timezone.utc)
        self.tickets = seed_demo(self.repo, now=self.now)

    def test_mistura_de_estados(self):
        abertos = self.repo.list_open()
        self.assertGreaterEqual(len(abertos), 4)  # painel tem o que mostrar
        self.assertLess(len(abertos), len(self.tickets))  # há encerrados também

    def test_variedade_de_categorias_e_prioridades(self):
        abertos = self.repo.list_open()
        categorias = {t.category for t in abertos}
        prioridades = {t.priority for t in abertos}
        self.assertGreaterEqual(len(categorias), 4)
        self.assertIn(Priority.ALTA, prioridades)
        self.assertIn(Priority.BAIXA, prioridades)

    def test_idades_retroativas_para_tempo_aberto(self):
        # O painel mostra "tempo aberto"; o seed precisa de chamados antigos.
        abertos = self.repo.list_open()
        idades = [self.now - t.created_at for t in abertos]
        self.assertTrue(any(idade > timedelta(hours=1) for idade in idades))
        self.assertTrue(any(idade < timedelta(minutes=30) for idade in idades))

    def test_todos_atribuidos_pelo_rodizio_real(self):
        self.assertTrue(all(t.assignee is not None for t in self.tickets))
        # Mais de um atendente recebeu chamados (rodízio de verdade).
        self.assertGreater(len({t.assignee.id for t in self.tickets}), 1)

    def test_dados_sao_fake(self):
        # Telefones fictícios padronizados e nomes genéricos de exemplo.
        for t in self.tickets:
            self.assertTrue(t.sender.startswith("55139900"), t.sender)
            self.assertTrue(t.sender_name.startswith("Funcionário Exemplo"), t.sender_name)

    def test_painel_renderiza_o_seed_sem_dados_sensiveis(self):
        abertos = self.repo.list_open()
        page = render_dashboard(abertos, now=self.now)
        for t in abertos:
            self.assertIn(f"<td>#{t.id}</td>", page)
            self.assertNotIn(t.sender, page)
            self.assertNotIn(t.sender_name, page)

    def test_seed_funciona_em_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = str(Path(tmpdir) / "demo-teste.sqlite3")
            repo = SqliteTicketRepository(db)
            try:
                seed_demo(repo)
                self.assertGreaterEqual(len(repo.list_open()), 4)
            finally:
                repo.close()


class TestSendMessage(unittest.TestCase):
    def setUp(self):
        repo = InMemoryTicketRepository()
        self.service = HelpdeskService(
            transport=FakeTransport(),
            attendants=[Attendant("ti1", "Atendente 1")],
            repository=repo,
        )
        self.server = make_server(
            MessageGateway(self.service), repo, host="127.0.0.1", port=0
        )
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_envia_e_cria_chamado(self):
        result = send_message("a rede caiu para todo mundo", base_url=self.base_url)
        self.assertFalse(result["duplicate"])
        self.assertEqual(result["category"], "rede")
        self.assertIsNotNone(self.service.repository.get(result["ticket_id"]))

    def test_event_ids_unicos_por_padrao(self):
        r1 = send_message("primeira mensagem", sender="a", base_url=self.base_url)
        r2 = send_message("segunda mensagem", sender="b", base_url=self.base_url)
        self.assertFalse(r1["duplicate"])
        self.assertFalse(r2["duplicate"])
        self.assertNotEqual(r1["ticket_id"], r2["ticket_id"])

    def test_event_id_forcado_demonstra_idempotencia(self):
        r1 = send_message("impressora parou", base_url=self.base_url, event_id="evt-demo")
        r2 = send_message("impressora parou", base_url=self.base_url, event_id="evt-demo")
        self.assertFalse(r1["duplicate"])
        self.assertTrue(r2["duplicate"])
        self.assertEqual(r1["ticket_id"], r2["ticket_id"])

    def test_mesmo_remetente_vira_followup(self):
        # Sequência natural da demonstração: duas mensagens do remetente padrão
        # caem no mesmo chamado (follow-up), sem duplicar.
        r1 = send_message("meu computador não liga", base_url=self.base_url)
        r2 = send_message("já tentei reiniciar e nada", base_url=self.base_url)
        self.assertEqual(r1["ticket_id"], r2["ticket_id"])
        self.assertFalse(r2["duplicate"])  # evento novo, mesmo chamado


if __name__ == "__main__":
    unittest.main()
