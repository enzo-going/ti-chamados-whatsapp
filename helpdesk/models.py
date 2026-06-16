"""Modelos de domínio do helpdesk.

Tudo aqui é puro (sem I/O), o que torna a lógica fácil de testar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def _now() -> datetime:
    """Horário atual em UTC (centralizado para facilitar testes determinísticos)."""
    return datetime.now(timezone.utc)


class Category(str, Enum):
    """Categorias de chamado típicas de um setor de TI interno."""

    REDE = "rede"
    HARDWARE = "hardware"
    SOFTWARE = "software"
    ACESSO = "acesso"
    IMPRESSORA = "impressora"
    EMPRESTIMO_EQUIPAMENTO = "emprestimo_equipamento"
    OUTROS = "outros"


class Priority(str, Enum):
    ALTA = "alta"
    MEDIA = "media"
    BAIXA = "baixa"


class Status(str, Enum):
    ABERTO = "aberto"
    ATRIBUIDO = "atribuido"
    EM_ANDAMENTO = "em_andamento"
    RESOLVIDO = "resolvido"
    FECHADO = "fechado"


class ServiceMode(str, Enum):
    """Como o chamado será atendido: no local do funcionário ou à distância.

    ``PRESENCIAL`` costuma vir acompanhado de um ``location`` (sala, setor ou
    evento); ``REMOTO`` indica que dá para resolver à distância. É metadado
    **operacional** (define para onde o atendente vai), não dado do solicitante.
    """

    PRESENCIAL = "presencial"
    REMOTO = "remoto"


# Papel/cargo usado quando o quadro não informa um (ex.: "supervisor",
# "efetivo", "estagiario", "aprendiz", "suporte").
DEFAULT_ROLE = "atendente"


@dataclass(frozen=True)
class Attendant:
    """Pessoa do setor de TI que recebe e resolve chamados.

    ``role`` é um papel/cargo genérico e ``active`` indica se a pessoa entra no
    rodízio de novas atribuições. O chamado guarda apenas a referência (id e
    nome) de quem o atende; papel e atividade são propriedades do **quadro**
    de atendentes — desativar alguém não afeta chamados já atribuídos.
    """

    id: str
    name: str
    role: str = DEFAULT_ROLE
    active: bool = True


@dataclass
class Message:
    """Mensagem recebida de um funcionário pelo WhatsApp.

    `sender` é o identificador do remetente (ex.: telefone). `text` é o corpo.
    """

    sender: str
    text: str
    sender_name: str | None = None
    received_at: datetime = field(default_factory=_now)


@dataclass
class Ticket:
    """Chamado aberto a partir de uma ou mais mensagens de um funcionário."""

    id: int
    sender: str
    category: Category
    priority: Priority
    subject: str
    status: Status = Status.ABERTO
    assignee: Attendant | None = None
    sender_name: str | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    closed_at: datetime | None = None
    history: list[str] = field(default_factory=list)
    # Local/modo de atendimento (opcional): definido por um atendente, não pela
    # mensagem do funcionário. `location` é texto livre (sala, setor, evento).
    service_mode: ServiceMode | None = None
    location: str | None = None

    def touch(self, note: str) -> None:
        """Registra um evento no histórico e atualiza o timestamp."""
        self.updated_at = _now()
        self.history.append(note)

    @property
    def is_open(self) -> bool:
        return self.status not in (Status.RESOLVIDO, Status.FECHADO)
