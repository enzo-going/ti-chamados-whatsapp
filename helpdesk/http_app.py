"""Servidor HTTP **local** (stdlib) para exercitar a camada de entrada.

Liga apenas em ``127.0.0.1`` por padrão. **Não** é um webhook público nem se
conecta a qualquer plataforma externa — serve para testar, de ponta a ponta e
com payloads próprios, a conversão de eventos em chamados e a idempotência.

Uso::

    python -m helpdesk.http_app --db chamados.sqlite3 --port 8000

    # em outra janela, envie um evento (exemplo com curl):
    #   curl -X POST http://127.0.0.1:8000/inbound \
    #        -H "Content-Type: application/json" \
    #        -d '{"event_id":"evt-1","sender":"5513990000001","text":"preciso de um notebook"}'
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from helpdesk import config
from helpdesk.inbound import InvalidPayload, MessageGateway
from helpdesk.models import Attendant
from helpdesk.repository import SqliteTicketRepository
from helpdesk.service import HelpdeskService
from helpdesk.transport import FakeTransport

_INBOUND_PATH = "/inbound"


def make_handler(gateway: MessageGateway) -> type[BaseHTTPRequestHandler]:
    """Cria o handler HTTP ligado a um ``MessageGateway``."""

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/health":
                self._json(200, {"status": "ok"})
            else:
                self._json(404, {"error": "rota não encontrada"})

        def do_POST(self) -> None:
            if self.path != _INBOUND_PATH:
                self._json(404, {"error": "rota não encontrada"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                self._json(400, {"error": "JSON inválido"})
                return
            try:
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

        def _json(self, status: int, body: dict) -> None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args) -> None:  # silencia o log padrão
            return

    return _Handler


def make_server(
    gateway: MessageGateway, host: str = "127.0.0.1", port: int = 8000
) -> HTTPServer:
    """Cria o servidor HTTP local. ``port=0`` escolhe uma porta livre (testes)."""
    return HTTPServer((host, port), make_handler(gateway))


def _build_gateway(db_path: str) -> tuple[MessageGateway, SqliteTicketRepository]:
    repo = SqliteTicketRepository(db_path)
    attendants = [Attendant("ti1", "Atendente 1"), Attendant("ti2", "Atendente 2")]
    service = HelpdeskService(
        transport=FakeTransport(), attendants=attendants, repository=repo
    )
    return MessageGateway(service), repo


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Servidor HTTP local da camada de entrada (não público)."
    )
    parser.add_argument("--host", default="127.0.0.1", help="padrão: 127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default=config.database_path())
    args = parser.parse_args()

    gateway, repo = _build_gateway(args.db)
    server = make_server(gateway, args.host, args.port)
    print(
        f"Camada de entrada ouvindo em http://{args.host}:{args.port}{_INBOUND_PATH} "
        "(Ctrl+C para sair)"
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
