"""Servidor HTTP **local** (stdlib) para exercitar a camada de entrada.

Liga apenas em ``127.0.0.1`` por padrão. **Não** é um webhook público nem se
conecta a qualquer plataforma externa — serve para testar, de ponta a ponta e
com payloads próprios, a conversão de eventos em chamados e a idempotência.

Também serve o **painel local somente leitura** em ``/dashboard`` (HTML), uma
visão restrita dos chamados em aberto — ver `helpdesk/dashboard.py`. É um
painel de desenvolvimento, não de produção.

Há ainda as rotas ``/webhook`` (GET de verificação + POST assinado), no
formato da integração de mensagens (ver `helpdesk/whatsapp.py`). Elas ficam
**inativas** (503) enquanto ``WHATSAPP_VERIFY_TOKEN`` / ``WHATSAPP_APP_SECRET``
não estiverem no ambiente — e o servidor continua escutando só em
``127.0.0.1``: a exposição pública (túnel HTTPS) é uma decisão à parte, fora
deste módulo.

Uso::

    python -m helpdesk.http_app --db chamados.sqlite3 --port 8000

    # painel somente leitura no navegador:
    #   http://127.0.0.1:8000/dashboard

    # em outra janela, envie um evento (exemplo com curl):
    #   curl -X POST http://127.0.0.1:8000/inbound \
    #        -H "Content-Type: application/json" \
    #        -d '{"event_id":"evt-1","sender":"5513990000001","text":"preciso de um notebook"}'
"""

from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from helpdesk import config
from helpdesk.attendants import load_roster
from helpdesk.dashboard import render_dashboard
from helpdesk.inbound import InvalidPayload, MessageGateway
from helpdesk.repository import SqliteTicketRepository, TicketRepository
from helpdesk.service import HelpdeskService
from helpdesk.transport import FakeTransport, MessagingTransport
from helpdesk.whatsapp import (
    CloudApiTransport,
    InvalidWebhookPayload,
    extract_inbound_payloads,
    valid_signature,
    verify_webhook,
)

_INBOUND_PATH = "/inbound"
_DASHBOARD_PATH = "/dashboard"
_WEBHOOK_PATH = "/webhook"


def make_handler(
    gateway: MessageGateway,
    repository: TicketRepository,
    *,
    webhook_verify_token: str | None = None,
    webhook_app_secret: str | None = None,
) -> type[BaseHTTPRequestHandler]:
    """Cria o handler HTTP ligado a um ``MessageGateway`` e ao repositório.

    O repositório entra separado porque o painel é somente leitura: ele lista
    os chamados em aberto sem passar pelo fluxo de entrada.

    As rotas ``/webhook`` só funcionam com ``webhook_verify_token`` (GET de
    verificação) e ``webhook_app_secret`` (assinatura do POST) — sem eles,
    respondem 503 (fail closed) e nada entra por ali.

    O servidor atende cada requisição em uma thread (ver ``make_server``), e
    este lock serializa o trabalho de verdade (serviço + banco): as threads
    existem para que conexões ociosas do navegador não bloqueiem ninguém, não
    para processar em paralelo.
    """
    work_lock = threading.Lock()

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parts = urlsplit(self.path)
            if parts.path == "/health":
                self._json(200, {"status": "ok"})
            elif parts.path == _DASHBOARD_PATH:
                with work_lock:
                    page = render_dashboard(repository.list_open())
                self._html(200, page)
            elif parts.path == _WEBHOOK_PATH:
                self._webhook_verification(parts.query)
            else:
                self._json(404, {"error": "rota não encontrada"})

        def do_POST(self) -> None:
            parts = urlsplit(self.path)
            if parts.path == _INBOUND_PATH:
                self._inbound()
            elif parts.path == _WEBHOOK_PATH:
                self._webhook_event()
            else:
                self._json(404, {"error": "rota não encontrada"})

        # ------------------------- rotas de entrada ------------------------ #

        def _inbound(self) -> None:
            payload = self._read_json()
            if payload is None:
                return
            try:
                with work_lock:
                    result = gateway.ingest(payload)
            except InvalidPayload as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(
                200,
                {
                    "ticket_id": result.ticket.id,
                    "category": result.ticket.category.value,
                    "duplicate": result.duplicate,
                },
            )

        def _webhook_verification(self, query: str) -> None:
            if not webhook_verify_token:
                self._json(503, {"error": "webhook não configurado"})
                return
            params = {key: values[0] for key, values in parse_qs(query).items()}
            challenge = verify_webhook(params, webhook_verify_token)
            if challenge is None:
                self._json(403, {"error": "verificação recusada"})
                return
            self._respond(
                200, "text/plain; charset=utf-8", challenge.encode("utf-8")
            )

        def _webhook_event(self) -> None:
            if not webhook_app_secret:
                self._json(503, {"error": "webhook não configurado"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            signature = self.headers.get("X-Hub-Signature-256")
            if not valid_signature(webhook_app_secret, raw, signature):
                self._json(403, {"error": "assinatura inválida"})
                return
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                self._json(400, {"error": "JSON inválido"})
                return
            try:
                extraction = extract_inbound_payloads(payload)
            except InvalidWebhookPayload as exc:
                self._json(400, {"error": str(exc)})
                return
            tickets = []
            ignored = list(extraction.ignored)
            for neutral in extraction.payloads:
                try:
                    with work_lock:
                        result = gateway.ingest(neutral)
                except InvalidPayload as exc:
                    ignored.append(str(exc))
                    continue
                tickets.append(
                    {"ticket_id": result.ticket.id, "duplicate": result.duplicate}
                )
            # Sempre 200 com assinatura válida: a plataforma reentrega eventos
            # respondidos com erro, e recibos/tipos ignorados não são erro.
            self._json(
                200,
                {"processed": len(tickets), "ignored": len(ignored), "tickets": tickets},
            )

        def _read_json(self) -> dict | None:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                self._json(400, {"error": "JSON inválido"})
                return None

        def _json(self, status: int, body: dict) -> None:
            self._respond(status, "application/json; charset=utf-8",
                          json.dumps(body, ensure_ascii=False).encode("utf-8"))

        def _html(self, status: int, body: str) -> None:
            self._respond(status, "text/html; charset=utf-8", body.encode("utf-8"))

        def _respond(self, status: int, content_type: str, data: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args) -> None:  # silencia o log padrão
            return

    return _Handler


def make_server(
    gateway: MessageGateway,
    repository: TicketRepository,
    host: str = "127.0.0.1",
    port: int = 8000,
    *,
    webhook_verify_token: str | None = None,
    webhook_app_secret: str | None = None,
) -> HTTPServer:
    """Cria o servidor HTTP local. ``port=0`` escolhe uma porta livre (testes).

    Usa ``ThreadingHTTPServer`` (uma thread por conexão): navegadores mantêm
    conexões abertas sem enviar nada (keep-alive/preconnect) e, num servidor de
    thread única, isso bloqueava a fila — outros clientes (ex.: o
    ``demo send``) estouravam timeout com o painel aberto. As threads são
    daemon e o trabalho real é serializado pelo lock do handler.
    """
    handler = make_handler(
        gateway,
        repository,
        webhook_verify_token=webhook_verify_token,
        webhook_app_secret=webhook_app_secret,
    )
    return ThreadingHTTPServer((host, port), handler)


def _build_gateway(
    db_path: str, transport: MessagingTransport | None = None
) -> tuple[MessageGateway, SqliteTicketRepository]:
    # Carrega o quadro antes de abrir o banco: se a configuração estiver
    # inválida, falha sem deixar conexão pendente. O banco permite uso a partir
    # das threads de requisição (acesso serializado pelo lock do handler).
    attendants = load_roster()
    repo = SqliteTicketRepository(db_path, allow_cross_thread=True)
    service = HelpdeskService(
        transport=transport or FakeTransport(),
        attendants=attendants,
        repository=repo,
    )
    return MessageGateway(service), repo


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Servidor HTTP local da camada de entrada (não público)."
    )
    parser.add_argument("--host", default="127.0.0.1", help="padrão: 127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default=config.database_path())
    parser.add_argument(
        "--transport",
        choices=("fake", "cloud-api"),
        default="fake",
        help="fake (padrão): respostas só registradas em memória. cloud-api: "
        "envio real pela API — exige WHATSAPP_TOKEN e "
        "WHATSAPP_PHONE_NUMBER_ID no ambiente; usar apenas na validação "
        "supervisionada com número de teste.",
    )
    args = parser.parse_args()

    transport: MessagingTransport | None = None
    if args.transport == "cloud-api":
        # Falha cedo (e citando só os NOMES das variáveis) se faltar algo.
        transport = CloudApiTransport.from_env()

    verify_token = config.whatsapp_verify_token()
    app_secret = config.whatsapp_app_secret()

    gateway, repo = _build_gateway(args.db, transport)
    server = make_server(
        gateway,
        repo,
        args.host,
        args.port,
        webhook_verify_token=verify_token,
        webhook_app_secret=app_secret,
    )
    if verify_token and app_secret:
        webhook_status = "ativas (verificação + assinatura configuradas)"
    else:
        webhook_status = (
            "inativas — defina "
            f"{config.WHATSAPP_VERIFY_TOKEN_ENV} e {config.WHATSAPP_APP_SECRET_ENV}"
        )
    print(
        f"Camada de entrada ouvindo em http://{args.host}:{args.port}{_INBOUND_PATH} "
        f"· painel em http://{args.host}:{args.port}{_DASHBOARD_PATH} "
        "(Ctrl+C para sair)"
    )
    print(
        f"  transporte de saída: {args.transport} · rotas {_WEBHOOK_PATH}: "
        f"{webhook_status}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        repo.close()


if __name__ == "__main__":
    main()
