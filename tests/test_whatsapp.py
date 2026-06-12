"""Testes da borda local da integração de mensagens (``helpdesk/whatsapp.py``).

Tudo roda **sem rede e sem credenciais reais**: a função HTTP do transporte é
um fake injetado e o servidor local sobe em porta efêmera. Os pontos críticos:

- segurança fail closed: sem verify token / app secret, nada entra (503);
  assinatura inválida é recusada (403);
- o token de acesso nunca aparece em ``repr``/erros do transporte;
- o id da mensagem vira ``event_id`` e liga a idempotência existente às
  reentregas da plataforma.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

from helpdesk import config
from helpdesk.http_app import make_server
from helpdesk.inbound import MessageGateway
from helpdesk.models import Attendant
from helpdesk.repository import InMemoryTicketRepository
from helpdesk.service import HelpdeskService
from helpdesk.transport import FakeTransport
from helpdesk.whatsapp import (
    CloudApiTransport,
    InvalidWebhookPayload,
    TransportError,
    extract_inbound_payloads,
    valid_signature,
    verify_webhook,
)

VERIFY_TOKEN = "token-de-verificacao-ficticio"
APP_SECRET = "segredo-de-app-ficticio"
ACCESS_TOKEN = "TOKEN-DE-ACESSO-FICTICIO-NAO-PODE-VAZAR"


def webhook_payload(
    text: str = "a impressora do almoxarifado parou",
    sender: str = "5513990002001",
    message_id: str = "wamid.exemplo-001",
    name: str | None = "Funcionário Exemplo 21",
    timestamp: str = "1780000000",
) -> dict:
    """Payload de webhook no formato da Cloud API, com dados fictícios."""
    value: dict = {
        "messaging_product": "whatsapp",
        "metadata": {
            "display_phone_number": "5513990009000",
            "phone_number_id": "111222333444555",
        },
        "messages": [
            {
                "from": sender,
                "id": message_id,
                "timestamp": timestamp,
                "type": "text",
                "text": {"body": text},
            }
        ],
    }
    if name is not None:
        value["contacts"] = [{"profile": {"name": name}, "wa_id": sender}]
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "0", "changes": [{"value": value, "field": "messages"}]}],
    }


def sign(body: bytes, secret: str = APP_SECRET) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class TestVerificacaoDoWebhook(unittest.TestCase):
    def test_handshake_valido_devolve_o_challenge(self):
        params = {
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "12345",
        }
        self.assertEqual(verify_webhook(params, VERIFY_TOKEN), "12345")

    def test_token_errado_e_recusado(self):
        params = {
            "hub.mode": "subscribe",
            "hub.verify_token": "outro-token",
            "hub.challenge": "12345",
        }
        self.assertIsNone(verify_webhook(params, VERIFY_TOKEN))

    def test_modo_diferente_de_subscribe_e_recusado(self):
        params = {
            "hub.mode": "unsubscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "12345",
        }
        self.assertIsNone(verify_webhook(params, VERIFY_TOKEN))

    def test_parametros_ausentes_sao_recusados(self):
        self.assertIsNone(verify_webhook({}, VERIFY_TOKEN))

    def test_sem_token_configurado_recusa_tudo(self):
        params = {
            "hub.mode": "subscribe",
            "hub.verify_token": "",
            "hub.challenge": "1",
        }
        self.assertIsNone(verify_webhook(params, ""))


class TestAssinatura(unittest.TestCase):
    BODY = b'{"entry": []}'

    def test_assinatura_correta_passa(self):
        self.assertTrue(valid_signature(APP_SECRET, self.BODY, sign(self.BODY)))

    def test_corpo_adulterado_falha(self):
        self.assertFalse(
            valid_signature(APP_SECRET, b'{"entry": [1]}', sign(self.BODY))
        )

    def test_cabecalho_ausente_falha(self):
        self.assertFalse(valid_signature(APP_SECRET, self.BODY, None))

    def test_prefixo_errado_falha(self):
        digest = sign(self.BODY).removeprefix("sha256=")
        self.assertFalse(valid_signature(APP_SECRET, self.BODY, f"sha1={digest}"))

    def test_sem_segredo_configurado_falha(self):
        self.assertFalse(valid_signature("", self.BODY, sign(self.BODY)))


class TestExtracaoDePayloads(unittest.TestCase):
    def test_mensagem_de_texto_vira_payload_neutro(self):
        extraction = extract_inbound_payloads(webhook_payload())
        self.assertEqual(extraction.ignored, [])
        (neutral,) = extraction.payloads
        self.assertEqual(neutral["event_id"], "wamid.exemplo-001")
        self.assertEqual(neutral["sender"], "5513990002001")
        self.assertEqual(neutral["sender_name"], "Funcionário Exemplo 21")
        self.assertEqual(neutral["text"], "a impressora do almoxarifado parou")
        self.assertIn("timestamp", neutral)
        self.assertIn("+00:00", str(neutral["timestamp"]))

    def test_sem_bloco_de_contatos_omite_o_nome(self):
        extraction = extract_inbound_payloads(webhook_payload(name=None))
        (neutral,) = extraction.payloads
        self.assertNotIn("sender_name", neutral)

    def test_recibos_de_status_sao_ignorados_sem_erro(self):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "statuses": [
                                    {"id": "wamid.x", "status": "delivered"}
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        extraction = extract_inbound_payloads(payload)
        self.assertEqual(extraction.payloads, [])
        self.assertEqual(len(extraction.ignored), 1)
        self.assertIn("status", extraction.ignored[0])

    def test_tipo_nao_suportado_e_ignorado_com_motivo(self):
        payload = webhook_payload()
        message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
        message["type"] = "image"
        del message["text"]
        extraction = extract_inbound_payloads(payload)
        self.assertEqual(extraction.payloads, [])
        self.assertIn("image", extraction.ignored[0])

    def test_varias_mensagens_no_mesmo_evento(self):
        payload = webhook_payload()
        value = payload["entry"][0]["changes"][0]["value"]
        value["messages"].append(
            {
                "from": "5513990002002",
                "id": "wamid.exemplo-002",
                "timestamp": "1780000100",
                "type": "text",
                "text": {"body": "a rede caiu no depósito"},
            }
        )
        extraction = extract_inbound_payloads(payload)
        self.assertEqual(len(extraction.payloads), 2)

    def test_motivos_ignorados_nao_carregam_conteudo_da_mensagem(self):
        payload = webhook_payload()
        message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
        message["type"] = "image"
        message["image"] = {"caption": "TEXTO-QUE-NAO-PODE-VAZAR"}
        del message["text"]
        extraction = extract_inbound_payloads(payload)
        self.assertNotIn("TEXTO-QUE-NAO-PODE-VAZAR", " ".join(extraction.ignored))
        self.assertNotIn("5513990002001", " ".join(extraction.ignored))

    def test_payload_que_nao_e_objeto_levanta_erro(self):
        with self.assertRaises(InvalidWebhookPayload):
            extract_inbound_payloads(["lista"])
        with self.assertRaises(InvalidWebhookPayload):
            extract_inbound_payloads({"entry": "não é lista"})

    def test_id_da_mensagem_liga_a_idempotencia_existente(self):
        service = HelpdeskService(
            transport=FakeTransport(),
            attendants=[Attendant("ti1", "Atendente 1")],
            repository=InMemoryTicketRepository(),
        )
        gateway = MessageGateway(service)
        (neutral,) = extract_inbound_payloads(webhook_payload()).payloads
        primeiro = gateway.ingest(neutral)
        repetido = gateway.ingest(neutral)
        self.assertFalse(primeiro.duplicate)
        self.assertTrue(repetido.duplicate)
        self.assertEqual(primeiro.ticket.id, repetido.ticket.id)


class TestTransporte(unittest.TestCase):
    def make_transport(self, status: int = 200, response: str = "{}"):
        calls: list[tuple[str, dict, bytes]] = []

        def fake_post(url, headers, body):
            calls.append((url, dict(headers), body))
            return status, response

        transport = CloudApiTransport(
            token=ACCESS_TOKEN,
            phone_number_id="111222333444555",
            http_post=fake_post,
        )
        return transport, calls

    def test_envio_monta_url_e_payload_da_api(self):
        transport, calls = self.make_transport()
        transport.send("5513990002001", "✅ Recebemos seu chamado *#1*.")
        ((url, headers, body),) = calls
        self.assertIn("/111222333444555/messages", url)
        self.assertIn("graph.facebook.com", url)
        self.assertIn(transport.graph_version, url)
        self.assertEqual(headers["Authorization"], f"Bearer {ACCESS_TOKEN}")
        payload = json.loads(body)
        self.assertEqual(payload["messaging_product"], "whatsapp")
        self.assertEqual(payload["to"], "5513990002001")
        self.assertEqual(payload["text"]["body"], "✅ Recebemos seu chamado *#1*.")

    def test_status_de_erro_vira_transport_error_sem_token(self):
        transport, _ = self.make_transport(status=401, response='{"error": "x"}')
        with self.assertRaises(TransportError) as ctx:
            transport.send("5513990002001", "olá")
        self.assertIn("401", str(ctx.exception))
        self.assertNotIn(ACCESS_TOKEN, str(ctx.exception))

    def test_repr_nao_contem_o_token(self):
        transport, _ = self.make_transport()
        self.assertNotIn(ACCESS_TOKEN, repr(transport))
        self.assertNotIn(ACCESS_TOKEN, str(transport))

    def test_from_env_exige_variaveis_e_cita_so_os_nomes(self):
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in set(config.INTEGRATION_ENV_VARS)
        }
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                CloudApiTransport.from_env()
        message = str(ctx.exception)
        self.assertIn(config.WHATSAPP_TOKEN_ENV, message)
        self.assertIn(config.WHATSAPP_PHONE_NUMBER_ID_ENV, message)

    def test_from_env_com_variaveis_definidas_constroi(self):
        env_extra = {
            config.WHATSAPP_TOKEN_ENV: ACCESS_TOKEN,
            config.WHATSAPP_PHONE_NUMBER_ID_ENV: "111222333444555",
        }
        with mock.patch.dict(os.environ, env_extra):
            transport = CloudApiTransport.from_env(http_post=lambda *a: (200, "{}"))
        self.assertEqual(transport.phone_number_id, "111222333444555")
        self.assertNotIn(ACCESS_TOKEN, repr(transport))


class TestRotasDeWebhookNoServidor(unittest.TestCase):
    """Sobe o servidor local em porta efêmera e exercita /webhook de ponta a ponta."""

    def setUp(self):
        service = HelpdeskService(
            transport=FakeTransport(),
            attendants=[Attendant("ti1", "Atendente 1")],
            repository=InMemoryTicketRepository(),
        )
        self.server = make_server(
            MessageGateway(service),
            service.repository,
            port=0,
            webhook_verify_token=VERIFY_TOKEN,
            webhook_app_secret=APP_SECRET,
        )
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def get(self, path: str):
        try:
            with urllib.request.urlopen(self.base_url + path, timeout=5) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, exc.read().decode("utf-8")

    def post(self, path: str, body: bytes, headers: dict | None = None):
        request = urllib.request.Request(
            self.base_url + path, data=body, headers=headers or {}, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())

    def test_handshake_de_verificacao_ecoa_o_challenge(self):
        status, body = self.get(
            "/webhook?hub.mode=subscribe"
            f"&hub.verify_token={VERIFY_TOKEN}&hub.challenge=987654"
        )
        self.assertEqual(status, 200)
        self.assertEqual(body, "987654")

    def test_handshake_com_token_errado_e_403(self):
        status, _ = self.get(
            "/webhook?hub.mode=subscribe&hub.verify_token=errado&hub.challenge=1"
        )
        self.assertEqual(status, 403)

    def test_evento_assinado_vira_chamado_e_reentrega_nao_duplica(self):
        body = json.dumps(webhook_payload()).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sign(body),
        }
        status, primeiro = self.post("/webhook", body, headers)
        self.assertEqual(status, 200)
        self.assertEqual(primeiro["processed"], 1)
        self.assertFalse(primeiro["tickets"][0]["duplicate"])

        status, repetido = self.post("/webhook", body, headers)
        self.assertEqual(status, 200)
        self.assertTrue(repetido["tickets"][0]["duplicate"])
        self.assertEqual(
            repetido["tickets"][0]["ticket_id"], primeiro["tickets"][0]["ticket_id"]
        )

    def test_assinatura_invalida_e_403(self):
        body = json.dumps(webhook_payload()).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sign(body, secret="outro-segredo"),
        }
        status, resposta = self.post("/webhook", body, headers)
        self.assertEqual(status, 403)
        self.assertIn("assinatura", resposta["error"])

    def test_sem_assinatura_e_403(self):
        body = json.dumps(webhook_payload()).encode("utf-8")
        status, _ = self.post(
            "/webhook", body, {"Content-Type": "application/json"}
        )
        self.assertEqual(status, 403)

    def test_so_recibos_de_status_responde_200_sem_processar(self):
        payload = {
            "entry": [
                {"changes": [{"value": {"statuses": [{"status": "read"}]}}]}
            ]
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sign(body),
        }
        status, resposta = self.post("/webhook", body, headers)
        self.assertEqual(status, 200)
        self.assertEqual(resposta["processed"], 0)
        self.assertEqual(resposta["ignored"], 1)

    def test_rotas_existentes_continuam_funcionando(self):
        status, _ = self.get("/health")
        self.assertEqual(status, 200)
        status, _ = self.get("/dashboard")
        self.assertEqual(status, 200)


class TestWebhookNaoConfigurado(unittest.TestCase):
    """Sem verify token / app secret, as rotas /webhook ficam fechadas (503)."""

    def setUp(self):
        service = HelpdeskService(
            transport=FakeTransport(),
            attendants=[Attendant("ti1", "Atendente 1")],
            repository=InMemoryTicketRepository(),
        )
        self.server = make_server(
            MessageGateway(service), service.repository, port=0
        )
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_get_sem_configuracao_e_503(self):
        try:
            with urllib.request.urlopen(
                f"{self.base_url}/webhook?hub.mode=subscribe", timeout=5
            ) as resp:
                status = resp.status
        except urllib.error.HTTPError as exc:
            with exc:
                status = exc.code
        self.assertEqual(status, 503)

    def test_post_sem_configuracao_e_503(self):
        request = urllib.request.Request(
            f"{self.base_url}/webhook", data=b"{}", method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as resp:
                status = resp.status
        except urllib.error.HTTPError as exc:
            with exc:
                status = exc.code
        self.assertEqual(status, 503)


if __name__ == "__main__":
    unittest.main()
