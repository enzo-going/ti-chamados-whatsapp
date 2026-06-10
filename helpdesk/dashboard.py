"""Painel local somente leitura dos chamados (base do futuro wallboard).

Gera a página HTML servida em ``/dashboard`` pelo servidor HTTP local
(`helpdesk/http_app.py`). É um **painel de desenvolvimento, não de produção**:
roda apenas em ``127.0.0.1``, sem autenticação, e existe para visualizar os
chamados sem depender de WhatsApp real. A mesma projeção servirá de base para
a TV da sala de TI (wallboard), prevista no roadmap.

Privacidade (decisão 8 do registro de decisões): a tela recebe uma **projeção
restrita** do chamado — apenas dados operacionais (número, categoria,
prioridade, status, responsável, abertura e tempo em aberto). Telefone do
solicitante, nome do solicitante, assunto e histórico de mensagens **não**
passam pela projeção, então não têm como vazar para a página.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone

from helpdesk.models import Priority, Status, Ticket
from helpdesk.replies import category_label, priority_label

# Intervalo de recarga automática da página (segundos). Leve o bastante para
# um painel de parede sem sobrecarregar o servidor local.
REFRESH_SECONDS = 15

_PRIORITY_RANK = {Priority.ALTA: 0, Priority.MEDIA: 1, Priority.BAIXA: 2}

_STATUS_LABEL = {
    Status.ABERTO: "Aberto",
    Status.ATRIBUIDO: "Atribuído",
    Status.EM_ANDAMENTO: "Em andamento",
    Status.RESOLVIDO: "Resolvido",
    Status.FECHADO: "Fechado",
}


@dataclass(frozen=True)
class PanelRow:
    """Projeção restrita de um chamado para exibição em tela compartilhada.

    Somente os campos abaixo chegam à página — adicionar qualquer dado novo ao
    painel exige passar por aqui (e pelo teste que fixa esta lista).
    """

    ticket_id: int
    category: str
    priority: str
    status: str
    assignee: str
    opened_at: str
    open_for: str


def format_duration(delta: timedelta) -> str:
    """Duração legível para o painel: ``42min``, ``3h 05min``, ``2d 4h``."""
    total_minutes = max(0, int(delta.total_seconds() // 60))
    days, remainder = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remainder, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes:02d}min"
    return f"{minutes}min"


def _format_opened(created_at: datetime, now: datetime) -> str:
    """Horário de abertura no fuso local: ``14:32`` (hoje) ou ``08/06 14:32``."""
    local = created_at.astimezone()
    if local.date() == now.astimezone().date():
        return local.strftime("%H:%M")
    return local.strftime("%d/%m %H:%M")


def project(ticket: Ticket, now: datetime) -> PanelRow:
    """Converte um ``Ticket`` na projeção restrita exibida no painel."""
    return PanelRow(
        ticket_id=ticket.id,
        category=category_label(ticket.category),
        priority=priority_label(ticket.priority),
        status=_STATUS_LABEL[ticket.status],
        assignee=ticket.assignee.name if ticket.assignee else "—",
        opened_at=_format_opened(ticket.created_at, now),
        open_for=format_duration(now - ticket.created_at),
    )


def panel_rows(tickets: list[Ticket], now: datetime | None = None) -> list[PanelRow]:
    """Projeta e ordena os chamados para o painel: prioridade, depois mais antigo."""
    now = now or datetime.now(timezone.utc)
    ordered = sorted(
        tickets, key=lambda t: (_PRIORITY_RANK[t.priority], t.created_at)
    )
    return [project(t, now) for t in ordered]


_PAGE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="{refresh}">
<title>Chamados — painel local</title>
<style>
  body {{ background: #14181d; color: #e8eaed; font-family: system-ui, sans-serif;
         margin: 2rem; }}
  h1 {{ font-size: 1.6rem; font-weight: 600; margin-bottom: 1rem; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 1.15rem; }}
  th {{ text-align: left; color: #9aa0a6; font-weight: 600; padding: .5rem .75rem;
       border-bottom: 2px solid #3c4043; }}
  td {{ padding: .55rem .75rem; border-bottom: 1px solid #2a2f35; }}
  tr.alta td {{ background: rgba(217, 48, 37, .12); }}
  .prio {{ font-weight: 600; text-transform: uppercase; font-size: .9em; }}
  tr.alta .prio {{ color: #f28b82; }}
  tr.media .prio {{ color: #fdd663; }}
  tr.baixa .prio {{ color: #81c995; }}
  .resumo {{ color: #9aa0a6; font-size: 1.05rem; margin: 0 0 1rem; }}
  .vazio {{ color: #9aa0a6; font-size: 1.2rem; padding: 2rem 0; }}
  .meta {{ color: #9aa0a6; font-size: .85rem; margin-top: 1.5rem; }}
</style>
</head>
<body>
<h1>Chamados em aberto</h1>
{content}
<p class="meta">Painel local somente leitura (desenvolvimento) · gerado às
{generated} · recarrega a cada {refresh}s</p>
</body>
</html>
"""

_TABLE = """<table>
<thead><tr><th>#</th><th>Categoria</th><th>Prioridade</th><th>Status</th>
<th>Responsável</th><th>Aberto às</th><th>Tempo aberto</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>"""


def _row_html(row: PanelRow) -> str:
    css = html.escape(row.priority.replace("é", "e"))  # alta/media/baixa
    cells = (
        f"<td>#{row.ticket_id}</td>"
        f"<td>{html.escape(row.category)}</td>"
        f'<td class="prio">{html.escape(row.priority)}</td>'
        f"<td>{html.escape(row.status)}</td>"
        f"<td>{html.escape(row.assignee)}</td>"
        f"<td>{html.escape(row.opened_at)}</td>"
        f"<td>{html.escape(row.open_for)}</td>"
    )
    return f'<tr class="{css}">{cells}</tr>'


def _summary(rows: list[PanelRow]) -> str:
    """Linha de resumo acima da tabela: total em aberto e quantos são alta."""
    plural = "s" if len(rows) != 1 else ""
    text = f"{len(rows)} chamado{plural} em aberto"
    altas = sum(1 for r in rows if r.priority == "alta")
    if altas:
        text += f" · {altas} de prioridade alta"
    return f'<p class="resumo">{text}</p>'


def render_dashboard(tickets: list[Ticket], now: datetime | None = None) -> str:
    """Página HTML completa do painel para os chamados em aberto."""
    now = now or datetime.now(timezone.utc)
    rows = panel_rows(tickets, now)
    if rows:
        content = _summary(rows) + _TABLE.format(
            rows="\n".join(_row_html(r) for r in rows)
        )
    else:
        content = '<p class="vazio">Nenhum chamado em aberto.</p>'
    return _PAGE.format(
        refresh=REFRESH_SECONDS,
        content=content,
        generated=now.astimezone().strftime("%H:%M:%S"),
    )


def panel_field_names() -> set[str]:
    """Nomes dos campos da projeção (usado em teste para fixar o contrato)."""
    return {f.name for f in fields(PanelRow)}
