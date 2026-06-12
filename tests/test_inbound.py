"""Testes da camada de entrada: parsing de payload, idempotência e HTTP local."""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from helpdesk.http_app import make_server
from helpdesk.inbound import InvalidPayload, MessageGateway, parse_payload
from helpdesk.models import Attendant, Category
from helpdesk.repository import InMemoryTicketRepository, SqliteTicketRepository
from helpdesk.service import HelpdeskService
from helpdesk.transport import FakeTransport

VALID = {
    "event_id": "evt-1",
    "sender": "5513990000001",
    "sender_name": "Funcionário X",
    "text": "preciso de um notebook emprestado",
}


def make_gateway(repository=None):
    service = HelpdeskService(
        transport=FakeTransport(),
        attendants=[Attendant("ti1", "Atendente 1"), Attendant("ti2", "Atendente 2")],
        repository=repository,
    )
    return MessageGateway(service), service


class TestParsePayload(unittest.TestCase):
    def test_valido(self):
        ev = parse_payload(VALID)
        self.assertEqual(ev.event_id, "evt-1")
        self.assertEqual(ev.message.sender, "5513990000001")
        self.assertEqual(ev.message.text, "preciso de um notebook emprestado")
        self.assertEqual(ev.message.sender_name, "Funcionário X")

    def test_campos_obrigatorios_ausentes(self):
        for faltando in ("event_id", "sender", "text"):
            payload = dict(VALID)
            del payload[faltando]
            with self.assertRaises(InvalidPayload, msg=faltando):
                parse_payload(payload)

    def test_campo_vazio_invalido(self):
        with self.assertRaises(InvalidPayload):
            parse_payload(dict(VALID, text="   "))

    def test_timestamp_valido(self):
        ev = parse_payload(dict(VALID, timestamp="2026-06-09T12:00:00+00:00"))
        self.assertEqual(ev.message.received_at.year, 2026)

    def test_timestamp_com_fuso_preservado(self):
        ev = parse_payload(dict(VALID, timestamp="2026-06-09T12:00:00-03:00"))
        # O instante (UTC) é preservado: 12:00 em -03:00 = 15:00 UTC.
        self.assertEqual(
            ev.message.received_at.astimezone(timezone.utc).hour, 15
        )

    def test_timestamp_sem_fuso_normalizado_para_utc(self):
        # Regressão: um timestamp "naive" (sem fuso) era devolvido sem tzinfo e
        # quebrava o cálculo de tempo do painel e a janela de follow-up
        # ("can't subtract offset-naive and offset-aware"). Agora é assumido UTC.
        ev = parse_payload(dict(VALID, timestamp="2026-06-09T12:00:00"))
        self.assertEqual(ev.message.received_at.tzinfo, timezone.utc)
        # E continua subtraível com um "agora" aware (o que o painel/serviço fazem).
        delta = datetime.now(timezone.utc) - ev.message.received_at
        self.assertGreater(delta.total_seconds(), 0)

    def test_timestamp_invalido(self):
        with self.assertRaises(InvalidPayload):
            parse_payload(dict(VALID, timestamp="ontem"))


class TestIdempotenciaMemoria(unittest.TestCase):
    def test_cria_chamado(self):
        gateway, service = make_gateway()
        r = gateway.ingest(VALID)
        self.assertFalse(r.duplicate)
        self.assertEqual(r.ticket.category, Category.EMPRESTIMO_EQUIPAMENTO)
        self.assertEqual(len(service.repository.all()), 1)

    def test_evento_repetido_nao_duplica(self):
        gateway, service = make_gateway()
        r1 = gateway.ingest(VALID)
        r2 = gateway.ingest(VALID)  # mesmo event_id
        self.assertFalse(r1.duplicate)
        self.assertTrue(r2.duplicate)
        self.assertEqual(r1.ticket.id, r2.ticket.id)
        self.assertEqual(len(service.repository.all()), 1)

    def test_eventos_de_remetentes_distintos_criam_varios(self):
        gateway, service = make_gateway()
        gateway.ingest(VALID)
        gateway.ingest(
            dict(VALID, event_id="evt-2", sender="5513990000002", text="a rede caiu")
        )
        self.assertEqual(len(service.repository.all()), 2)

    def test_mesmo_remetente_em_sequencia_vira_followup(self):
        # Eventos distintos do mesmo remetente, em sequência, são anexados ao
        # mesmo chamado (follow-up) em vez de duplicar.
        gateway, service = make_gateway()
        r1 = gateway.ingest(VALID)
        r2 = gateway.ingest(
            dict(VALID, event_id="evt-2", text="esqueci de dizer: é no 2o andar")
        )
        self.assertEqual(r1.ticket.id, r2.ticket.id)
        self.assertEqual(len(service.repository.all()), 1)


class TestIdempotenciaSqlite(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self.db = str(Path(self._dir) / "t.sqlite3")

    def tearDown(self):
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_idempotencia_persistente(self):
        repo = SqliteTicketRepository(self.db)
        gateway, _ = make_gateway(repo)
        gateway.ingest(VALID)
        self.assertEqual(len(repo.all()), 1)
        repo.close()

        # Nova conexão simula reinício do processo: o evento continua "visto".
        repo2 = SqliteTicketRepository(self.db)
        try:
            self.assertIsNotNone(repo2.seen_event("evt-1"))
            gateway2, _ = make_gateway(repo2)
            r = gateway2.ingest(VALID)
            self.assertTrue(r.duplicate)
            self.assertEqual(len(repo2.all()), 1)
        finally:
            repo2.close()


class TestHttpLocal(unittest.TestCase):
    def setUp(self):
        repo = InMemoryTicketRepository()
        gateway, _ = make_gateway(repo)
        self.server = make_server(gateway, repo, host="127.0.0.1", port=0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _post(self, payload):
        url = f"http://127.0.0.1:{self.port}/inbound"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())

    def test_post_cria_e_idempotente(self):
        status1, body1 = self._post(VALID)
        status2, body2 = self._post(VALID)  # reentrega do mesmo evento
        self.assertEqual(status1, 200)
        self.assertEqual(status2, 200)
        self.assertFalse(body1["duplicate"])
        self.assertTrue(body2["duplicate"])
        self.assertEqual(body1["ticket_id"], body2["ticket_id"])


if __name__ == "__main__":
    unittest.main()
