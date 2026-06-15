"""Testes do fluxo do serviço: criação, atribuição, resposta e reabertura."""

import unittest
from datetime import timedelta

from helpdesk.models import Attendant, Category, Message, Priority, Status
from helpdesk.repository import InMemoryTicketRepository
from helpdesk.service import HelpdeskService
from helpdesk.transport import FakeTransport


def make_service(reopen_hours: int = 2) -> tuple[HelpdeskService, FakeTransport]:
    transport = FakeTransport()
    attendants = [
        Attendant("ti1", "Atendente 1"),
        Attendant("ti2", "Atendente 2"),
        Attendant("ti3", "Atendente 3"),
        Attendant("ti4", "Atendente 4"),
    ]
    service = HelpdeskService(
        transport=transport,
        attendants=attendants,
        reopen_window=timedelta(hours=reopen_hours),
    )
    return service, transport


class TestCreateAndReply(unittest.TestCase):
    def test_cria_chamado_com_categoria_e_prioridade(self):
        service, _ = make_service()
        ticket = service.handle_message(Message(sender="5513999", text="a rede caiu, ninguem consegue acessar"))
        self.assertEqual(ticket.category, Category.REDE)
        self.assertEqual(ticket.priority, Priority.ALTA)
        self.assertEqual(ticket.status, Status.ATRIBUIDO)
        self.assertIsNotNone(ticket.assignee)

    def test_envia_confirmacao_ao_remetente(self):
        service, transport = make_service()
        service.handle_message(Message(sender="5513999", text="impressora sem toner"))
        resposta = transport.last_to("5513999")
        self.assertIsNotNone(resposta)
        self.assertIn("#1", resposta)
        self.assertIn("Impressora", resposta)

    def test_round_robin_distribui_entre_atendentes(self):
        service, _ = make_service()
        t1 = service.handle_message(Message(sender="a", text="pc nao liga"))
        t2 = service.handle_message(Message(sender="b", text="sem internet"))
        t3 = service.handle_message(Message(sender="c", text="senha bloqueada"))
        self.assertNotEqual(t1.assignee, t2.assignee)
        self.assertNotEqual(t2.assignee, t3.assignee)

    def test_emprestimo_equipamento_gera_chamado_e_resposta(self):
        service, transport = make_service()
        t = service.handle_message(
            Message(sender="x", text="preciso de um notebook emprestado para reunião")
        )
        self.assertEqual(t.category, Category.EMPRESTIMO_EQUIPAMENTO)
        self.assertIn("Empréstimo de equipamento", transport.last_to("x"))

    def test_toda_categoria_tem_rotulo_de_resposta(self):
        # Garante que cada categoria do domínio tem rótulo público em replies.
        from helpdesk.replies import _CATEGORY_LABEL

        for categoria in Category:
            self.assertIn(categoria, _CATEGORY_LABEL, msg=str(categoria))


class TestReopen(unittest.TestCase):
    def test_reabre_dentro_da_janela(self):
        service, transport = make_service(reopen_hours=2)
        t = service.handle_message(Message(sender="5513999", text="rede caiu"))
        service.resolve(t.id, "reiniciei o switch")

        # Mesma pessoa escreve de novo 30 min depois -> reabre o mesmo chamado.
        nova = Message(
            sender="5513999",
            text="voltou a cair",
            received_at=t.closed_at + timedelta(minutes=30),
        )
        resultado = service.handle_message(nova)
        self.assertEqual(resultado.id, t.id)
        self.assertEqual(resultado.status, Status.ABERTO)
        self.assertIn("Reabrimos", transport.last_to("5513999"))

    def test_nao_reabre_fora_da_janela(self):
        service, _ = make_service(reopen_hours=2)
        t = service.handle_message(Message(sender="5513999", text="rede caiu"))
        service.resolve(t.id)

        nova = Message(
            sender="5513999",
            text="outro problema agora",
            received_at=t.closed_at + timedelta(hours=5),
        )
        resultado = service.handle_message(nova)
        self.assertNotEqual(resultado.id, t.id)  # criou chamado novo

    def test_remetente_diferente_nao_reabre(self):
        service, _ = make_service()
        t = service.handle_message(Message(sender="pessoa-a", text="rede caiu"))
        service.resolve(t.id)
        resultado = service.handle_message(
            Message(sender="pessoa-b", text="minha rede tambem caiu", received_at=t.closed_at + timedelta(minutes=10))
        )
        self.assertNotEqual(resultado.id, t.id)


class TestFollowup(unittest.TestCase):
    def test_anexa_em_chamado_aberto(self):
        service, transport = make_service()
        t1 = service.handle_message(Message(sender="z", text="meu computador não liga"))
        t2 = service.handle_message(Message(sender="z", text="já tentei reiniciar e nada"))
        self.assertEqual(t1.id, t2.id)  # mesmo chamado
        self.assertEqual(len(service.repository.all()), 1)  # não duplicou
        self.assertIn("Anotamos", transport.last_to("z"))  # resposta de follow-up
        historico = service.repository.get(t1.id).history
        self.assertTrue(any("já tentei reiniciar" in h for h in historico))

    def test_followup_mantem_responsavel(self):
        service, _ = make_service()
        t1 = service.handle_message(Message(sender="z", text="meu computador não liga"))
        t2 = service.handle_message(Message(sender="z", text="continua sem ligar"))
        self.assertEqual(t2.assignee, t1.assignee)  # não reatribui

    def test_respeita_janela_de_continuidade(self):
        service, _ = make_service(reopen_hours=2)
        t1 = service.handle_message(Message(sender="z", text="meu computador não liga"))
        tardia = Message(
            sender="z",
            text="agora é outro assunto",
            received_at=t1.updated_at + timedelta(hours=5),
        )
        t2 = service.handle_message(tardia)
        self.assertNotEqual(t1.id, t2.id)  # fora da janela -> chamado novo
        self.assertEqual(len(service.repository.all()), 2)

    def test_remetente_diferente_nao_anexa(self):
        service, _ = make_service()
        t1 = service.handle_message(Message(sender="z", text="meu computador não liga"))
        t2 = service.handle_message(Message(sender="w", text="a impressora travou"))
        self.assertNotEqual(t1.id, t2.id)
        self.assertEqual(len(service.repository.all()), 2)


class TestLifecycle(unittest.TestCase):
    def test_fluxo_completo(self):
        service, _ = make_service()
        t = service.handle_message(Message(sender="x", text="sistema lento"))
        self.assertEqual(t.status, Status.ATRIBUIDO)
        service.start_progress(t.id)
        self.assertEqual(service.repository.get(t.id).status, Status.EM_ANDAMENTO)
        service.resolve(t.id, "limpei arquivos temporarios")
        resolved = service.repository.get(t.id)
        self.assertEqual(resolved.status, Status.RESOLVIDO)
        self.assertIsNotNone(resolved.closed_at)

    def test_servico_exige_atendente(self):
        with self.assertRaises(ValueError):
            HelpdeskService(transport=FakeTransport(), attendants=[])

    def test_operacao_em_chamado_inexistente_levanta_keyerror(self):
        service, _ = make_service()
        for op in (service.start_progress, service.resolve, service.close):
            with self.subTest(op=op.__name__):
                with self.assertRaises(KeyError):
                    op(9999)


class TestActiveRoster(unittest.TestCase):
    """Rodízio com ativos/inativos: inativo não recebe novas atribuições."""

    def test_rodizio_so_entre_ativos(self):
        quadro = [
            Attendant("ti1", "Atendente 1"),
            Attendant("ti2", "Atendente 2", active=False),
            Attendant("ti3", "Atendente 3"),
        ]
        service = HelpdeskService(transport=FakeTransport(), attendants=quadro)
        ids = [
            service.handle_message(Message(sender=s, text="pc nao liga")).assignee.id
            for s in ("a", "b", "c", "d")
        ]
        self.assertEqual(ids, ["ti1", "ti3", "ti1", "ti3"])  # ti2 nunca entra

    def test_servico_exige_atendente_ativo(self):
        quadro = [Attendant("ti1", "Atendente 1", active=False)]
        with self.assertRaises(ValueError):
            HelpdeskService(transport=FakeTransport(), attendants=quadro)

    def test_inativar_nao_quebra_chamado_ja_atribuido(self):
        # Simula a troca de turno/quadro: o serviço é recriado com a mesma
        # base de chamados, mas com o antigo responsável agora inativo.
        repo = InMemoryTicketRepository()
        quadro_v1 = [Attendant("ti1", "Atendente 1"), Attendant("ti2", "Atendente 2")]
        service_v1 = HelpdeskService(
            transport=FakeTransport(), attendants=quadro_v1, repository=repo
        )
        t = service_v1.handle_message(Message(sender="z", text="rede caiu"))
        self.assertEqual(t.assignee.id, "ti1")

        quadro_v2 = [
            Attendant("ti1", "Atendente 1", active=False),
            Attendant("ti2", "Atendente 2"),
        ]
        service_v2 = HelpdeskService(
            transport=FakeTransport(), attendants=quadro_v2, repository=repo
        )
        # Follow-up no chamado existente: mantém o responsável original.
        seguimento = service_v2.handle_message(Message(sender="z", text="ainda sem rede"))
        self.assertEqual(seguimento.id, t.id)
        self.assertEqual(seguimento.assignee.id, "ti1")
        # Chamado novo de outra pessoa: vai para quem está ativo.
        novo = service_v2.handle_message(Message(sender="w", text="impressora parou"))
        self.assertEqual(novo.assignee.id, "ti2")


if __name__ == "__main__":
    unittest.main()
