"""Servidor HTTP **local** (stdlib) para exercitar a camada de entrada.

Liga apenas em ``127.0.0.1`` por padrão. **Não** é um webhook público nem se
conecta a qualquer plataforma externa — serve para testar, de ponta a ponta e
com payloads próprios, a conversão de eventos em chamados e a idempotência.

Também serve o **painel local somente leitura** em ``/dashboard`` (HTML), uma
visão restrita dos chamados em aberto — ver `helpdesk/dashboard.py`. É um
painel de desenvolvimento, não de produção.

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

from helpdesk import config
from helpdesk.attendants import load_roster
from helpdesk.dashboard import render_dashboard
from helpdesk.inbound import InvalidPayload, MessageGateway
from helpdesk.repository import SqliteTicketRepository, TicketRepository
from helpdesk.service import HelpdeskService
from helpdesk.transport import FakeTransport

_INBOUND_PATH = "/inbound"
_DASHBOARD_PATH = "/dashboard"


def make_handler(
    gateway: MessageGateway, repository: TicketRepository
) -> type[BaseHTTPRequestHandler]:
    """Cria o handler HTTP ligado a um ``MessageGateway`` e ao repositório.

    O repositório entra separado porque o painel é somente leitura: ele lista
    os chamados em aberto sem passar pelo fluxo de entrada.

    O servidor atende cada requisição em uma thread (ver ``make_server``), e
    este lock serializa o trabalho de verdade (serviço + banco): as threads
    existem para que conexões ociosas do navegador não bloqueiem ninguém, não
    para processar em paralelo.
    """
    work_lock = threading.Lock()

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/health":
                self._json(200, {"status": "ok"})
            elif self.path == _DASHBOARD_PATH:
                with work_lock:
                    page = render_dashboard(repository.list_open())
                self._html(200, page)
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
) -> HTTPServer:
    """Cria o servidor HTTP local. ``port=0`` escolhe uma porta livre (testes).

    Usa ``ThreadingHTTPServer`` (uma thread por conexão): navegadores mantêm
    conexões abertas sem enviar nada (keep-alive/preconnect) e, num servidor de
    thread única, isso bloqueava a fila — outros clientes (ex.: o
    ``demo send``) estouravam timeout com o painel aberto. As threads são
    daemon e o trabalho real é serializado pelo lock do handler.
    """
    return ThreadingHTTPServer((host, port), make_handler(gateway, repository))


def _build_gateway(db_path: str) -> tuple[MessageGateway, SqliteTicketRepository]:
    # Carrega o quadro antes de abrir o banco: se a configuração estiver
    # inválida, falha sem deixar conexão pendente. O banco permite uso a partir
    # das threads de requisição (acesso serializado pelo lock do handler).
    attendants = load_roster()
    repo = SqliteTicketRepository(db_path, allow_cross_thread=True)
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
    server = make_server(gateway, repo, args.host, args.port)
    print(
        f"Camada de entrada ouvindo em http://{args.host}:{args.port}{_INBOUND_PATH} "
        f"· painel em http://{args.host}:{args.port}{_DASHBOARD_PATH} "
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
