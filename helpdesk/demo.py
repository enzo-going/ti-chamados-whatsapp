"""Demonstração local do helpdesk: banco de exemplo e simulação de mensagens.

Tudo aqui é **fake e local**: telefones fictícios, textos genéricos, nenhum
contato com WhatsApp ou serviço externo. Permite subir uma demonstração
completa (banco + servidor + painel) em poucos comandos::

    python -m helpdesk.demo seed --reset            # cria demo.sqlite3 com chamados fake
    python -m helpdesk.http_app --db demo.sqlite3   # sobe o servidor local
    #   painel: http://127.0.0.1:8000/dashboard
    python -m helpdesk.demo send "a impressora parou"   # simula mensagem chegando

O ``seed`` passa pelo **fluxo real** do serviço (triagem, atribuição em rodízio,
ciclo de vida), não por inserts diretos — o que aparece no painel é o
comportamento verdadeiro do sistema. O ``send`` envia um payload ao servidor
HTTP local, exercitando a mesma entrada que uma integração futura usaria.

Passo a passo completo em ``docs/demo-local.md``.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

# Saída com acentos/“·” em qualquer console (mesmo ajuste do main.py).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from helpdesk.attendants import load_roster
from helpdesk.models import Message, Ticket
from helpdesk.repository import SqliteTicketRepository, TicketRepository
from helpdesk.service import HelpdeskService
from helpdesk.transport import FakeTransport

# Banco padrão da demonstração — separado do banco "real" (helpdesk.sqlite3)
# para poder ser recriado à vontade. Ambos são ignorados pelo git.
DEFAULT_DEMO_DB = "demo.sqlite3"

DEFAULT_BASE_URL = "http://127.0.0.1:8000"

# Remetente padrão do `send`: fixo de propósito, para a sequência natural da
# demonstração (duas mensagens seguidas viram follow-up no mesmo chamado).
DEFAULT_SENDER = "5513990000099"


@dataclass(frozen=True)
class _Cenario:
    """Um chamado fake do roteiro: mensagem + idade + ponto do ciclo de vida."""

    sender: str
    sender_name: str
    text: str
    age: timedelta
    lifecycle: str  # "novo" | "andamento" | "resolvido" | "fechado"


# Roteiro com categorias, prioridades, idades e status variados. Os textos são
# escolhidos para a triagem real classificar como anotado nos comentários.
_CENARIOS: tuple[_Cenario, ...] = (
    # software · média · fechado (não aparece no painel)
    _Cenario(
        "5513990001001", "Funcionário Exemplo 1",
        "o sistema de ponto travou ontem à tarde",
        timedelta(days=2, hours=2), "fechado",
    ),
    # impressora · média · resolvido (não aparece no painel)
    _Cenario(
        "5513990001002", "Funcionário Exemplo 2",
        "não consigo imprimir o relatório, acho que a impressora está sem toner",
        timedelta(days=1, hours=5), "resolvido",
    ),
    # empréstimo de equipamento · média · em andamento
    _Cenario(
        "5513990001003", "Funcionário Exemplo 3",
        "preciso de um notebook emprestado para o treinamento de amanhã",
        timedelta(days=1, hours=2), "andamento",
    ),
    # acesso · média · atribuído
    _Cenario(
        "5513990001004", "Funcionário Exemplo 4",
        "esqueci minha senha do email, podem redefinir?",
        timedelta(hours=4), "novo",
    ),
    # hardware · média · em andamento
    _Cenario(
        "5513990001005", "Funcionário Exemplo 5",
        "o computador da recepção não liga de jeito nenhum",
        timedelta(hours=2, minutes=30), "andamento",
    ),
    # rede · ALTA · atribuído
    _Cenario(
        "5513990001006", "Funcionário Exemplo 6",
        "a rede caiu no segundo andar, ninguém consegue acessar o sistema",
        timedelta(hours=1, minutes=10), "novo",
    ),
    # outros · ALTA · atribuído
    _Cenario(
        "5513990001007", "Funcionário Exemplo 7",
        "urgente: o telão da sala de reunião não dá imagem e a diretoria está esperando",
        timedelta(minutes=25), "novo",
    ),
    # outros · baixa · atribuído
    _Cenario(
        "5513990001008", "Funcionário Exemplo 8",
        "uma dúvida sem pressa: quando puder, como faço backup dos meus arquivos?",
        timedelta(minutes=5), "novo",
    ),
)


def seed_demo(
    repository: TicketRepository, now: datetime | None = None
) -> list[Ticket]:
    """Popula o repositório com os chamados fake do roteiro.

    Processa do mais antigo para o mais novo, pelo fluxo real do serviço —
    triagem, rodízio de atribuição e mudanças de status acontecem de verdade.
    Devolve todos os chamados criados (abertos e encerrados).
    """
    now = now or datetime.now(timezone.utc)
    service = HelpdeskService(
        transport=FakeTransport(),
        attendants=load_roster(),
        repository=repository,
    )
    tickets: list[Ticket] = []
    for cenario in _CENARIOS:
        ticket = service.handle_message(
            Message(
                sender=cenario.sender,
                sender_name=cenario.sender_name,
                text=cenario.text,
                received_at=now - cenario.age,
            )
        )
        if cenario.lifecycle == "andamento":
            service.start_progress(ticket.id)
        elif cenario.lifecycle == "resolvido":
            service.resolve(ticket.id, "Resolvido durante a demonstração.")
        elif cenario.lifecycle == "fechado":
            service.resolve(ticket.id, "Resolvido durante a demonstração.")
            service.close(ticket.id)
        tickets.append(repository.get(ticket.id) or ticket)
    return tickets


def send_message(
    text: str,
    sender: str = DEFAULT_SENDER,
    sender_name: str | None = None,
    base_url: str = DEFAULT_BASE_URL,
    event_id: str | None = None,
) -> dict:
    """Envia um payload de mensagem ao servidor HTTP local e devolve a resposta.

    Gera um ``event_id`` único por chamada (a menos que um seja passado — útil
    para demonstrar a idempotência reenviando o mesmo evento).
    """
    payload: dict[str, object] = {
        "event_id": event_id or f"demo-{uuid4().hex[:12]}",
        "sender": sender,
        "text": text,
    }
    if sender_name:
        payload["sender_name"] = sender_name
    request = urllib.request.Request(
        f"{base_url}/inbound",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read())


# --------------------------------------------------------------------------- #
# Linha de comando
# --------------------------------------------------------------------------- #


def _cmd_seed(args: argparse.Namespace) -> None:
    path = Path(args.db)
    if path.exists():
        if not args.reset:
            sys.exit(
                f"O arquivo {args.db} já existe. Use --reset para recriar do zero."
            )
        path.unlink()
    repository = SqliteTicketRepository(str(path))
    try:
        tickets = seed_demo(repository)
        abertos = [t for t in tickets if t.is_open]
        altas = [t for t in abertos if t.priority.value == "alta"]
        print(f"Banco de demonstração criado: {args.db}")
        print(
            f"  {len(tickets)} chamados no total · {len(abertos)} em aberto · "
            f"{len(altas)} de prioridade alta"
        )
        print("\nPróximos passos:")
        print(f"  python -m helpdesk.http_app --db {args.db}")
        print("  painel: http://127.0.0.1:8000/dashboard")
    finally:
        repository.close()


def _cmd_send(args: argparse.Namespace) -> None:
    base_url = f"http://127.0.0.1:{args.port}"
    try:
        result = send_message(
            args.text,
            sender=args.sender,
            sender_name=args.name,
            base_url=base_url,
            event_id=args.event_id,
        )
    except urllib.error.URLError as exc:
        sys.exit(
            f"Não consegui falar com o servidor em {base_url} ({exc.reason}).\n"
            f"Ele está rodando? Suba com: python -m helpdesk.http_app --db {DEFAULT_DEMO_DB}"
        )
    if result.get("duplicate"):
        print(
            f"Evento repetido — devolvido o chamado existente #{result['ticket_id']} "
            "(idempotência, nada foi duplicado)."
        )
    else:
        print(
            f"Mensagem registrada no chamado #{result['ticket_id']} "
            f"(categoria: {result['category']})."
        )
    print("Atualize o painel para ver: recarregue /dashboard no navegador.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Demonstração local do helpdesk (dados fake, sem WhatsApp real)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed", help="cria o banco de demonstração com chamados fake")
    seed.add_argument("--db", default=DEFAULT_DEMO_DB, help="padrão: %(default)s")
    seed.add_argument(
        "--reset", action="store_true", help="recria o banco se ele já existir"
    )
    seed.set_defaults(func=_cmd_seed)

    send = sub.add_parser(
        "send", help="simula uma mensagem chegando (POST no servidor local)"
    )
    send.add_argument("text", help="texto da mensagem, entre aspas")
    send.add_argument("--sender", default=DEFAULT_SENDER, help="padrão: %(default)s")
    send.add_argument("--name", default=None, help="nome fictício do remetente")
    send.add_argument("--port", type=int, default=8000)
    send.add_argument(
        "--event-id",
        default=None,
        help="força um event_id (reenvie o mesmo para demonstrar a idempotência)",
    )
    send.set_defaults(func=_cmd_send)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
