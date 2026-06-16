"""Demonstração local do helpdesk: banco de exemplo e simulação de mensagens.

Tudo aqui é **fake e local**: telefones fictícios, textos genéricos, nenhum
contato com WhatsApp ou serviço externo. Permite subir uma demonstração
completa (banco + servidor + painel) em poucos comandos::

    python -m helpdesk.demo check                   # pré-voo: o fluxo todo funciona?
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
import sqlite3
import sys
import tempfile
import threading
import urllib.error
import urllib.request

# Saída com acentos/“·” em qualquer console (mesmo ajuste do main.py).
# O stderr também: as mensagens de erro amigáveis têm acentos.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from helpdesk.attendants import load_roster
from helpdesk.http_app import make_server
from helpdesk.inbound import MessageGateway
from helpdesk.models import Message, ServiceMode, Ticket
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
    # Local/modo de atendimento opcional, para o painel da demo mostrar a coluna
    # "Local" preenchida (definido como um atendente faria, não pela mensagem).
    mode: ServiceMode | None = None
    local: str | None = None


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
    # acesso · média · atribuído · remoto (dá para resolver à distância)
    _Cenario(
        "5513990001004", "Funcionário Exemplo 4",
        "esqueci minha senha do email, podem redefinir?",
        timedelta(hours=4), "novo",
        mode=ServiceMode.REMOTO,
    ),
    # hardware · média · em andamento · presencial na recepção
    _Cenario(
        "5513990001005", "Funcionário Exemplo 5",
        "o computador da recepção não liga de jeito nenhum",
        timedelta(hours=2, minutes=30), "andamento",
        mode=ServiceMode.PRESENCIAL, local="Recepção",
    ),
    # rede · ALTA · atribuído · presencial no 2º andar
    _Cenario(
        "5513990001006", "Funcionário Exemplo 6",
        "a rede caiu no segundo andar, ninguém consegue acessar o sistema",
        timedelta(hours=1, minutes=10), "novo",
        mode=ServiceMode.PRESENCIAL, local="2º andar",
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
        if cenario.mode is not None or cenario.local is not None:
            service.set_attendance(
                ticket.id, mode=cenario.mode, location=cenario.local
            )
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
# Checagem automática (pré-voo da demonstração)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CheckStep:
    """Um passo da checagem: o que foi verificado e como terminou."""

    label: str
    ok: bool
    detail: str = ""


def run_check() -> list[CheckStep]:
    """Percorre o fluxo completo da demonstração em ambiente descartável.

    Sobe um servidor próprio em porta efêmera com banco temporário e exercita
    tudo o que a demonstração mostra: seed pelo fluxo real, mensagem nova,
    follow-up, idempotência e painel. Não toca no ``demo.sqlite3`` nem exige
    servidor rodando. A checagem para no primeiro passo que falhar (os
    seguintes dependeriam dele); devolve a lista de passos com os resultados.
    """
    steps: list[CheckStep] = []

    versao = ".".join(str(n) for n in sys.version_info[:3])
    if sys.version_info < (3, 10):
        steps.append(
            CheckStep(
                "Python 3.10+",
                False,
                f"versão encontrada: {versao} — instale o Python 3.10 ou mais novo",
            )
        )
        return steps
    steps.append(CheckStep("Python 3.10+", True, f"versão {versao}"))

    # O quadro vem da mesma configuração que a demo usaria (arquivo apontado
    # por HELPDESK_ATTENDANTS_PATH ou o exemplo embutido) — erro aqui é erro
    # que apareceria ao vivo.
    try:
        roster = load_roster()
        ativos = sum(1 for attendant in roster if attendant.active)
        if ativos == 0:
            raise RuntimeError(
                "nenhum atendente ativo — o rodízio precisa de ao menos um"
            )
    except Exception as exc:
        steps.append(CheckStep("quadro de atendentes", False, str(exc)))
        return steps
    steps.append(
        CheckStep(
            "quadro de atendentes",
            True,
            f"{len(roster)} no quadro, {ativos} ativo(s) no rodízio",
        )
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            repo = SqliteTicketRepository(
                str(Path(tmpdir) / "checagem.sqlite3"), allow_cross_thread=True
            )
        except Exception as exc:
            steps.append(CheckStep("banco temporário (SQLite)", False, str(exc)))
            return steps
        server = None
        thread = None
        try:
            try:
                tickets = seed_demo(repo)
                abertos = len(repo.list_open())
            except Exception as exc:
                steps.append(CheckStep("banco temporário (SQLite)", False, str(exc)))
                return steps
            steps.append(
                CheckStep(
                    "banco temporário (SQLite)",
                    True,
                    f"{len(tickets)} chamados fake pelo fluxo real, {abertos} em aberto",
                )
            )

            try:
                service = HelpdeskService(
                    transport=FakeTransport(), attendants=roster, repository=repo
                )
                server = make_server(MessageGateway(service), repo, port=0)
                base_url = f"http://127.0.0.1:{server.server_address[1]}"
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                with urllib.request.urlopen(f"{base_url}/health", timeout=5) as resp:
                    health = json.loads(resp.read())
                if health.get("status") != "ok":
                    raise RuntimeError(f"resposta inesperada do /health: {health}")
            except Exception as exc:
                steps.append(
                    CheckStep("servidor local em porta efêmera", False, str(exc))
                )
                return steps
            steps.append(
                CheckStep("servidor local em porta efêmera", True, base_url)
            )

            # Remetentes próprios da checagem, fora dos usados pelo seed.
            sender_novo = "5513990000071"
            try:
                novo = send_message(
                    "a impressora do financeiro parou",
                    sender=sender_novo,
                    base_url=base_url,
                )
                if novo.get("duplicate"):
                    raise RuntimeError("a primeira mensagem veio marcada como repetida")
                if novo.get("category") != "impressora":
                    raise RuntimeError(
                        f"triagem inesperada: {novo.get('category')!r} "
                        "(esperado: 'impressora')"
                    )
            except Exception as exc:
                steps.append(CheckStep("mensagem nova vira chamado", False, str(exc)))
                return steps
            steps.append(
                CheckStep(
                    "mensagem nova vira chamado",
                    True,
                    f"chamado #{novo['ticket_id']}, categoria impressora",
                )
            )

            try:
                seguida = send_message(
                    "continua sem imprimir", sender=sender_novo, base_url=base_url
                )
                if seguida["ticket_id"] != novo["ticket_id"]:
                    raise RuntimeError(
                        f"abriu o chamado #{seguida['ticket_id']} em vez de cair "
                        f"no #{novo['ticket_id']}"
                    )
                if seguida.get("duplicate"):
                    raise RuntimeError("follow-up veio marcado como evento repetido")
            except Exception as exc:
                steps.append(
                    CheckStep("follow-up cai no mesmo chamado", False, str(exc))
                )
                return steps
            steps.append(
                CheckStep(
                    "follow-up cai no mesmo chamado",
                    True,
                    f"segunda mensagem anexada ao chamado #{novo['ticket_id']}",
                )
            )

            try:
                primeiro = send_message(
                    "teste de reentrega",
                    sender="5513990000072",
                    base_url=base_url,
                    event_id="check-evt-1",
                )
                repetido = send_message(
                    "teste de reentrega",
                    sender="5513990000072",
                    base_url=base_url,
                    event_id="check-evt-1",
                )
                if primeiro.get("duplicate") or not repetido.get("duplicate"):
                    raise RuntimeError(
                        "esperado 'duplicate' apenas na reentrega; veio "
                        f"{primeiro} e depois {repetido}"
                    )
                if repetido["ticket_id"] != primeiro["ticket_id"]:
                    raise RuntimeError("a reentrega devolveu um chamado diferente")
            except Exception as exc:
                steps.append(CheckStep("idempotência na reentrega", False, str(exc)))
                return steps
            steps.append(
                CheckStep(
                    "idempotência na reentrega",
                    True,
                    "mesmo evento enviado duas vezes não duplicou nada",
                )
            )

            try:
                with urllib.request.urlopen(
                    f"{base_url}/dashboard", timeout=5
                ) as resp:
                    page = resp.read().decode("utf-8")
                if f"<td>#{novo['ticket_id']}</td>" not in page:
                    raise RuntimeError(
                        f"o chamado #{novo['ticket_id']} não apareceu no painel"
                    )
                if sender_novo in page:
                    raise RuntimeError(
                        "telefone do remetente apareceu no HTML do painel"
                    )
            except Exception as exc:
                steps.append(CheckStep("painel /dashboard", False, str(exc)))
                return steps
            steps.append(
                CheckStep(
                    "painel /dashboard",
                    True,
                    "chamados em aberto listados, sem telefone no HTML",
                )
            )
        finally:
            if server is not None:
                if thread is not None:
                    server.shutdown()
                server.server_close()
            if thread is not None:
                thread.join(timeout=5)
            repo.close()
    return steps


# --------------------------------------------------------------------------- #
# Linha de comando
# --------------------------------------------------------------------------- #


def _cmd_check(args: argparse.Namespace) -> None:
    print("Checagem da demonstração local (o demo.sqlite3 não é tocado):\n")
    steps = run_check()
    for step in steps:
        marcador = "[ok]" if step.ok else "[FALHOU]"
        detalhe = f" — {step.detail}" if step.detail else ""
        print(f"  {marcador:<8} {step.label}{detalhe}")
    print()
    falhas = [step for step in steps if not step.ok]
    if falhas:
        sys.exit(
            f"{len(falhas)} passo falhou. Corrija o item marcado acima e rode de "
            "novo: python -m helpdesk.demo check"
        )
    print(f"Tudo certo ({len(steps)}/{len(steps)} passos): a demonstração está pronta.")
    print("Para apresentar: .\\demo.ps1   (passo a passo: docs/demo-local.md)")


def _cmd_seed(args: argparse.Namespace) -> None:
    path = Path(args.db)
    if path.exists() and not args.reset:
        sys.exit(
            f"O arquivo {args.db} já existe. Use --reset para recriar do zero."
        )
    # Reset via SQL (clear), não apagando o arquivo: assim funciona mesmo com o
    # servidor da demo aberto. No Windows, apagar um .sqlite3 em uso falha com
    # PermissionError/WinError 32 — daí a mensagem amigável se o banco estiver
    # travado por um processo que esteja escrevendo no momento.
    try:
        repository = SqliteTicketRepository(str(path))
    except sqlite3.OperationalError:
        sys.exit(
            f"Não foi possível abrir {args.db} (em uso?). Feche a janela do "
            "servidor da demo e rode de novo."
        )
    try:
        if args.reset:
            repository.clear()
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
    except sqlite3.OperationalError:
        sys.exit(
            f"O banco {args.db} está em uso (servidor da demo escrevendo agora?). "
            "Feche a janela do servidor e rode de novo."
        )
    finally:
        repository.close()


def _cmd_clear(args: argparse.Namespace) -> None:
    path = Path(args.db)
    if not path.exists():
        sys.exit(
            f"O arquivo {args.db} não existe — nada para limpar. "
            "Crie a demo com: python -m helpdesk.demo seed"
        )
    # Limpa via SQL (clear), não apagando o arquivo: funciona mesmo com o
    # servidor da demo aberto (mesmo motivo do --reset, ver decisão 16).
    try:
        repository = SqliteTicketRepository(str(path))
    except sqlite3.OperationalError:
        sys.exit(
            f"Não foi possível abrir {args.db} (em uso?). Feche a janela do "
            "servidor da demo e rode de novo."
        )
    try:
        repository.clear()
        print(f"Banco da demonstração esvaziado: {args.db}")
        print("  0 chamados — os ids recomeçam do #1 no próximo chamado.")
        print("Recarregue /dashboard para ver o painel vazio.")
    except sqlite3.OperationalError:
        sys.exit(
            f"O banco {args.db} está em uso (servidor da demo escrevendo agora?). "
            "Feche a janela do servidor e rode de novo."
        )
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
    except urllib.error.HTTPError as exc:
        # O servidor respondeu, mas recusou o payload (ex.: campo inválido).
        try:
            detail = json.loads(exc.read()).get("error", "")
        except Exception:
            detail = ""
        sys.exit(f"O servidor recusou a mensagem (HTTP {exc.code}). {detail}".strip())
    except (TimeoutError, ConnectionError, urllib.error.URLError, OSError):
        sys.exit(
            f"O servidor local não está respondendo em {base_url}.\n"
            "  - confirme que a demo está rodando (.\\demo.ps1 ou "
            f"python -m helpdesk.http_app --db {DEFAULT_DEMO_DB})\n"
            "  - confirme a porta: o número em --port aqui precisa ser o mesmo "
            "do servidor\n"
            f"  - tente de novo: python -m helpdesk.demo send \"{args.text}\" "
            f"--port {args.port}"
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

    check = sub.add_parser(
        "check",
        help="pré-voo: percorre o fluxo completo em ambiente descartável e "
        "aponta o que falhar",
    )
    check.set_defaults(func=_cmd_check)

    seed = sub.add_parser("seed", help="cria o banco de demonstração com chamados fake")
    seed.add_argument("--db", default=DEFAULT_DEMO_DB, help="padrão: %(default)s")
    seed.add_argument(
        "--reset", action="store_true", help="recria o banco se ele já existir"
    )
    seed.set_defaults(func=_cmd_seed)

    clear = sub.add_parser(
        "clear", help="esvazia o banco de demonstração (apaga todos os chamados)"
    )
    clear.add_argument("--db", default=DEFAULT_DEMO_DB, help="padrão: %(default)s")
    clear.set_defaults(func=_cmd_clear)

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
