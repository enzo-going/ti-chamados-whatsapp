"""Demonstração interativa do helpdesk usando um transporte de mentira.

Roda sem WhatsApp real: simula mensagens de funcionários chegando e mostra o
chamado criado e a resposta automática. Útil para visualizar o fluxo.

    python main.py                 # roteiro de exemplo (em memória, efêmero)
    python main.py --repl          # modo interativo: você digita as mensagens
    python main.py --db chamados.sqlite3   # persiste os chamados em SQLite
"""

from __future__ import annotations

import argparse
import sys

# As respostas automáticas usam emojis (✅ 🔁). No console do Windows (cp1252)
# isso quebraria; forçamos UTF-8 na saída para a demonstração rodar em qualquer SO.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from helpdesk import config
from helpdesk.models import Attendant, Message
from helpdesk.repository import SqliteTicketRepository, TicketRepository
from helpdesk.service import HelpdeskService
from helpdesk.transport import FakeTransport

ATENDENTES = [
    Attendant("ti1", "Enzo"),
    Attendant("ti2", "Ana"),
    Attendant("ti3", "Bruno"),
    Attendant("ti4", "Carla"),
]

ROTEIRO = [
    ("5513990000001", "Bom dia! A rede caiu aqui no segundo andar, ninguém consegue acessar nada"),
    ("5513990000002", "a impressora do RH não está imprimindo, acho que é o toner"),
    ("5513990000003", "esqueci minha senha do email, consigo redefinir?"),
    ("5513990000004", "meu computador não liga de jeito nenhum"),
    ("5513990000005", "uma dúvida: quando puder, como faço backup dos meus arquivos?"),
]


def _print_ticket(service: HelpdeskService, transport: FakeTransport, sender: str) -> None:
    # Último chamado do remetente para exibir.
    todos = [t for t in service.repository.all() if t.sender == sender]
    if not todos:
        return
    ticket = todos[-1]
    nome = ticket.assignee.name if ticket.assignee else "—"
    print(f"  -> Chamado #{ticket.id} | {ticket.category.value} | prioridade {ticket.priority.value} | atendente: {nome}")
    print(f"    assunto: {ticket.subject}")
    resposta = transport.last_to(sender)
    if resposta:
        primeira_linha = resposta.splitlines()[0]
        print(f"    resposta automática: {primeira_linha}")


def _make_service(db_path: str | None) -> tuple[HelpdeskService, FakeTransport]:
    """Monta o serviço com transporte de mentira e o repositório escolhido.

    Sem `--db`, usa o repositório em memória (demo efêmera). Com `--db`, persiste
    os chamados no arquivo SQLite informado.
    """
    transport = FakeTransport()
    repository: TicketRepository | None = (
        SqliteTicketRepository(db_path) if db_path else None
    )
    service = HelpdeskService(
        transport=transport, attendants=ATENDENTES, repository=repository
    )
    return service, transport


def run_roteiro(db_path: str | None = None) -> None:
    service, transport = _make_service(db_path)
    print("=== Simulação de chamados (transporte de mentira) ===\n")
    for sender, texto in ROTEIRO:
        print(f"[{sender}] {texto}")
        service.handle_message(Message(sender=sender, text=texto))
        _print_ticket(service, transport, sender)
        print()
    print(f"Total de chamados abertos: {len(service.repository.all())}")


def run_repl(db_path: str | None = None) -> None:
    service, transport = _make_service(db_path)
    print("Modo interativo. Digite uma mensagem (ou 'sair').\n")
    while True:
        try:
            texto = input("funcionário> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if texto.lower() in {"sair", "exit", "quit"}:
            break
        if not texto:
            continue
        service.handle_message(Message(sender="repl-user", text=texto))
        _print_ticket(service, transport, "repl-user")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo do helpdesk de TI por WhatsApp.")
    parser.add_argument("--repl", action="store_true", help="modo interativo")
    parser.add_argument(
        "--db",
        metavar="ARQUIVO",
        nargs="?",
        const=config.database_path(),
        default=None,
        help=(
            "persiste os chamados em SQLite; sem valor usa HELPDESK_DB_PATH "
            "(padrão: %(const)s). Omitido, roda em memória."
        ),
    )
    args = parser.parse_args()
    if args.repl:
        run_repl(args.db)
    else:
        run_roteiro(args.db)


if __name__ == "__main__":
    main()
