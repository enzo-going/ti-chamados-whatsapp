"""Testes do painel local somente leitura.

O ponto mais importante aqui é a **privacidade**: a página exibe apenas a
projeção restrita (dados operacionais) e nunca telefone, nome do solicitante
ou conteúdo das mensagens.
"""

from __future__ import annotations

import threading
import unittest
import urllib.request
from datetime import datetime, timedelta, timezone

from helpdesk.dashboard import (
    PanelRow,
    format_duration,
    panel_field_names,
    panel_rows,
    render_dashboard,
)
from helpdesk.http_app import make_server
from helpdesk.inbound import MessageGateway
from helpdesk.models import Attendant, Message
from helpdesk.repository import InMemoryTicketRepository
from helpdesk.service import HelpdeskService
from helpdesk.transport import FakeTransport

TELEFONE = "5513990000001"
NOME_SOLICITANTE = "Funcionário Sigiloso"
TEXTO_SENSIVEL = "minha senha do email é hunter2, não consigo logar"


def make_service(repo=None) -> HelpdeskService:
    return HelpdeskService(
        transport=FakeTransport(),
        attendants=[Attendant("ti1", "Atendente 1"), Attendant("ti2", "Atendente 2")],
        repository=repo,
    )


def open_ticket(service: HelpdeskService, sender: str = TELEFONE, text: str = TEXTO_SENSIVEL):
    return service.handle_message(
        Message(sender=sender, text=text, sender_name=NOME_SOLICITANTE)
    )


class TestProjecao(unittest.TestCase):
    def test_contrato_de_campos_da_projecao(self):
        # Fixa a lista de campos que podem chegar à tela. Adicionar um campo
        # novo ao painel exige atualizar este teste conscientemente.
        self.assertEqual(
            panel_field_names(),
            {
                "ticket_id",
                "category",
                "priority",
                "status",
                "assignee",
                "opened_at",
                "open_for",
            },
        )

    def test_projecao_usa_rotulos_operacionais(self):
        service = make_service()
        ticket = open_ticket(service)
        (row,) = panel_rows([ticket])
        self.assertEqual(row.ticket_id, ticket.id)
        self.assertEqual(row.category, "Acesso / Senhas")
        self.assertEqual(row.priority, "média")
        self.assertEqual(row.status, "Atribuído")
        self.assertEqual(row.assignee, "Atendente 1")

    def test_sem_responsavel_mostra_travessao(self):
        service = make_service()
        ticket = open_ticket(service)
        ticket.assignee = None
        (row,) = panel_rows([ticket])
        self.assertEqual(row.assignee, "—")

    def test_ordena_por_prioridade_e_idade(self):
        service = make_service()
        baixa = service.handle_message(
            Message(sender="a", text="uma dúvida sem pressa: como troco o papel de parede?")
        )
        alta_nova = service.handle_message(
            Message(sender="b", text="a rede caiu, ninguém consegue trabalhar")
        )
        alta_antiga = service.handle_message(
            Message(
                sender="c",
                text="urgente: sistema fora do ar para todos",
                received_at=alta_nova.created_at - timedelta(hours=3),
            )
        )
        rows = panel_rows([baixa, alta_nova, alta_antiga])
        ids = [r.ticket_id for r in rows]
        # Altas primeiro (mais antiga antes), baixa por último.
        self.assertEqual(ids, [alta_antiga.id, alta_nova.id, baixa.id])


class TestFormatDuration(unittest.TestCase):
    def test_minutos(self):
        self.assertEqual(format_duration(timedelta(minutes=42)), "42min")

    def test_horas(self):
        self.assertEqual(format_duration(timedelta(hours=3, minutes=5)), "3h 05min")

    def test_dias(self):
        self.assertEqual(format_duration(timedelta(days=2, hours=4)), "2d 4h")

    def test_negativo_vira_zero(self):
        self.assertEqual(format_duration(timedelta(seconds=-30)), "0min")


class TestRenderHtml(unittest.TestCase):
    def test_exibe_dados_operacionais(self):
        service = make_service()
        ticket = open_ticket(service)
        page = render_dashboard([ticket])
        # `<td>#N</td>` evita casar com cores hex do CSS (ex.: "#14181d").
        self.assertIn(f"<td>#{ticket.id}</td>", page)
        self.assertIn("Acesso / Senhas", page)
        self.assertIn("Atendente 1", page)
        self.assertIn("Tempo aberto", page)

    def test_nao_vaza_dados_sensiveis(self):
        service = make_service()
        ticket = open_ticket(service)
        page = render_dashboard([ticket])
        self.assertNotIn(TELEFONE, page)            # telefone do solicitante
        self.assertNotIn(NOME_SOLICITANTE, page)    # nome do solicitante
        self.assertNotIn("hunter2", page)           # conteúdo da mensagem
        self.assertNotIn("senha do email", page)    # assunto derivado do texto
        for trecho in ticket.history:
            self.assertNotIn(trecho, page)          # histórico completo

    def test_escapa_html_de_valores_dinamicos(self):
        service = HelpdeskService(
            transport=FakeTransport(),
            attendants=[Attendant("x1", "<script>alert(1)</script>")],
        )
        ticket = open_ticket(service)
        page = render_dashboard([ticket])
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)

    def test_estado_vazio(self):
        page = render_dashboard([])
        self.assertIn("Nenhum chamado em aberto", page)

    def test_resumo_de_contagem(self):
        service = make_service()
        service.handle_message(Message(sender="a", text="impressora sem toner"))
        service.handle_message(
            Message(sender="b", text="a rede caiu, ninguém consegue trabalhar")
        )
        page = render_dashboard(service.repository.list_open())
        self.assertIn("2 chamados em aberto · 1 de prioridade alta", page)

    def test_resumo_singular_sem_alta(self):
        service = make_service()
        service.handle_message(Message(sender="a", text="impressora sem toner"))
        page = render_dashboard(service.repository.list_open())
        self.assertIn("1 chamado em aberto", page)
        self.assertNotIn("prioridade alta", page)

    def test_pagina_tem_auto_refresh(self):
        self.assertIn('http-equiv="refresh"', render_dashboard([]))

    def test_horario_de_abertura_de_dia_anterior_inclui_data(self):
        service = make_service()
        ontem = datetime.now(timezone.utc) - timedelta(days=1, hours=2)
        ticket = service.handle_message(
            Message(sender="a", text="impressora parou", received_at=ontem)
        )
        (row,) = panel_rows([ticket])
        self.assertIn("/", row.opened_at)  # formato dd/mm hh:mm


class TestHttpDashboard(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryTicketRepository()
        self.service = make_service(self.repo)
        gateway = MessageGateway(self.service)
        self.server = make_server(gateway, self.repo, host="127.0.0.1", port=0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _get(self, path: str):
        url = f"http://127.0.0.1:{self.port}{path}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, resp.headers.get("Content-Type"), resp.read().decode("utf-8")

    def test_dashboard_responde_html_com_chamados(self):
        ticket = open_ticket(self.service)
        status, content_type, body = self._get("/dashboard")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn(f"<td>#{ticket.id}</td>", body)

    def test_dashboard_nao_expoe_dados_sensiveis_via_http(self):
        open_ticket(self.service)
        _, _, body = self._get("/dashboard")
        self.assertNotIn(TELEFONE, body)
        self.assertNotIn(NOME_SOLICITANTE, body)
        self.assertNotIn("hunter2", body)

    def test_dashboard_lista_apenas_chamados_em_aberto(self):
        aberto = open_ticket(self.service)
        fechado = self.service.handle_message(
            Message(sender="outro", text="meu monitor piscando")
        )
        self.service.resolve(fechado.id)
        self.service.close(fechado.id)
        _, _, body = self._get("/dashboard")
        self.assertIn(f"<td>#{aberto.id}</td>", body)
        self.assertNotIn(f"<td>#{fechado.id}</td>", body)


if __name__ == "__main__":
    unittest.main()
