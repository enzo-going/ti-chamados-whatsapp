"""Testes do modo de demonstração local (seed de dados fake + envio simulado)."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from helpdesk.dashboard import render_dashboard
from helpdesk.demo import run_check, seed_demo, send_message
from helpdesk.http_app import make_server
from helpdesk.inbound import MessageGateway
from helpdesk.models import Attendant, Priority, ServiceMode
from helpdesk.repository import InMemoryTicketRepository, SqliteTicketRepository
from helpdesk.service import HelpdeskService
from helpdesk.transport import FakeTransport


class TestSeedDemo(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryTicketRepository()
        self.now = datetime.now(timezone.utc)
        self.tickets = seed_demo(self.repo, now=self.now)

    def test_mistura_de_estados(self):
        abertos = self.repo.list_open()
        self.assertGreaterEqual(len(abertos), 4)  # painel tem o que mostrar
        self.assertLess(len(abertos), len(self.tickets))  # há encerrados também

    def test_variedade_de_categorias_e_prioridades(self):
        abertos = self.repo.list_open()
        categorias = {t.category for t in abertos}
        prioridades = {t.priority for t in abertos}
        self.assertGreaterEqual(len(categorias), 4)
        self.assertIn(Priority.ALTA, prioridades)
        self.assertIn(Priority.BAIXA, prioridades)

    def test_idades_retroativas_para_tempo_aberto(self):
        # O painel mostra "tempo aberto"; o seed precisa de chamados antigos.
        abertos = self.repo.list_open()
        idades = [self.now - t.created_at for t in abertos]
        self.assertTrue(any(idade > timedelta(hours=1) for idade in idades))
        self.assertTrue(any(idade < timedelta(minutes=30) for idade in idades))

    def test_todos_atribuidos_pelo_rodizio_real(self):
        self.assertTrue(all(t.assignee is not None for t in self.tickets))
        # Mais de um atendente recebeu chamados (rodízio de verdade).
        self.assertGreater(len({t.assignee.id for t in self.tickets}), 1)

    def test_dados_sao_fake(self):
        # Telefones fictícios padronizados e nomes genéricos de exemplo.
        for t in self.tickets:
            self.assertTrue(t.sender.startswith("55139900"), t.sender)
            self.assertTrue(t.sender_name.startswith("Funcionário Exemplo"), t.sender_name)

    def test_painel_renderiza_o_seed_sem_dados_sensiveis(self):
        abertos = self.repo.list_open()
        page = render_dashboard(abertos, now=self.now)
        for t in abertos:
            self.assertIn(f"<td>#{t.id}</td>", page)
            self.assertNotIn(t.sender, page)
            self.assertNotIn(t.sender_name, page)

    def test_seed_funciona_em_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = str(Path(tmpdir) / "demo-teste.sqlite3")
            repo = SqliteTicketRepository(db)
            try:
                seed_demo(repo)
                self.assertGreaterEqual(len(repo.list_open()), 4)
            finally:
                repo.close()


class TestSendMessage(unittest.TestCase):
    def setUp(self):
        repo = InMemoryTicketRepository()
        self.service = HelpdeskService(
            transport=FakeTransport(),
            attendants=[Attendant("ti1", "Atendente 1")],
            repository=repo,
        )
        self.server = make_server(
            MessageGateway(self.service), repo, host="127.0.0.1", port=0
        )
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_envia_e_cria_chamado(self):
        result = send_message("a rede caiu para todo mundo", base_url=self.base_url)
        self.assertFalse(result["duplicate"])
        self.assertEqual(result["outcome"], "criado")
        self.assertEqual(result["category"], "rede")
        self.assertIsNotNone(self.service.repository.get(result["ticket_id"]))

    def test_event_ids_unicos_por_padrao(self):
        r1 = send_message("primeira mensagem", sender="a", base_url=self.base_url)
        r2 = send_message("segunda mensagem", sender="b", base_url=self.base_url)
        self.assertFalse(r1["duplicate"])
        self.assertFalse(r2["duplicate"])
        self.assertNotEqual(r1["ticket_id"], r2["ticket_id"])

    def test_event_id_forcado_demonstra_idempotencia(self):
        r1 = send_message("impressora parou", base_url=self.base_url, event_id="evt-demo")
        r2 = send_message("impressora parou", base_url=self.base_url, event_id="evt-demo")
        self.assertFalse(r1["duplicate"])
        self.assertTrue(r2["duplicate"])
        self.assertIsNone(r2["outcome"])  # reentrega não tem desfecho novo
        self.assertEqual(r1["ticket_id"], r2["ticket_id"])

    def test_mesmo_remetente_vira_followup(self):
        # Sequência natural da demonstração: duas mensagens do remetente padrão
        # caem no mesmo chamado (follow-up), sem duplicar.
        r1 = send_message("meu computador não liga", base_url=self.base_url)
        r2 = send_message("já tentei reiniciar e nada", base_url=self.base_url)
        self.assertEqual(r1["ticket_id"], r2["ticket_id"])
        self.assertFalse(r2["duplicate"])  # evento novo, mesmo chamado
        self.assertEqual(r1["outcome"], "criado")
        self.assertEqual(r2["outcome"], "followup")  # relatado como follow-up, não "novo"

    def test_conexao_ociosa_nao_bloqueia_o_servidor(self):
        # Regressão: o navegador com o painel aberto mantém conexões TCP sem
        # enviar nada (keep-alive/preconnect). Num servidor de thread única
        # isso travava a fila e o `demo send` estourava timeout.
        host, port = self.server.server_address
        idle = socket.create_connection((host, port))
        try:
            result = send_message("a impressora parou", base_url=self.base_url)
            self.assertIn("ticket_id", result)
        finally:
            idle.close()

    def test_varios_sends_simultaneos(self):
        resultados: dict[str, dict] = {}
        erros: list[Exception] = []

        def enviar(sender: str) -> None:
            try:
                resultados[sender] = send_message(
                    "sem internet na minha sala", sender=sender, base_url=self.base_url
                )
            except Exception as exc:  # noqa: BLE001 - teste registra qualquer falha
                erros.append(exc)

        threads = [
            threading.Thread(target=enviar, args=(f"55139900002{i:02d}",))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertEqual(erros, [])
        ids = {r["ticket_id"] for r in resultados.values()}
        self.assertEqual(len(ids), 5)  # remetentes distintos, chamados distintos

    def test_mesmo_evento_concorrente_nao_duplica(self):
        # Garantia crítica para a integração: a plataforma reentrega eventos
        # ("ao menos uma vez"), às vezes em paralelo. O mesmo event_id disparado
        # por várias threads deve gerar UM chamado — exatamente um "novo", o
        # resto "duplicate" — sem corrida.
        resultados: list[dict] = []
        erros: list[Exception] = []
        lock = threading.Lock()

        def enviar() -> None:
            try:
                r = send_message(
                    "evento reentregue", sender="5513990000900",
                    base_url=self.base_url, event_id="evt-concorrente",
                )
                with lock:
                    resultados.append(r)
            except Exception as exc:  # noqa: BLE001
                erros.append(exc)

        threads = [threading.Thread(target=enviar) for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        self.assertEqual(erros, [])
        novos = [r for r in resultados if not r["duplicate"]]
        ids = {r["ticket_id"] for r in resultados}
        self.assertEqual(len(novos), 1, "deve haver exatamente um chamado novo")
        self.assertEqual(len(ids), 1, "todas as respostas apontam o mesmo chamado")


class TestServidorComSqliteEmThreads(unittest.TestCase):
    """O servidor com threads precisa conseguir usar o repositório SQLite."""

    def test_send_e_dashboard_sobre_sqlite(self):
        import urllib.request

        with tempfile.TemporaryDirectory() as tmpdir:
            db = str(Path(tmpdir) / "demo-threads.sqlite3")
            repo = SqliteTicketRepository(db, allow_cross_thread=True)
            service = HelpdeskService(
                transport=FakeTransport(),
                attendants=[Attendant("ti1", "Atendente 1")],
                repository=repo,
            )
            server = make_server(
                MessageGateway(service), repo, host="127.0.0.1", port=0
            )
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                result = send_message("a rede caiu para todos", base_url=base_url)
                self.assertEqual(result["category"], "rede")
                with urllib.request.urlopen(f"{base_url}/dashboard", timeout=5) as resp:
                    page = resp.read().decode("utf-8")
                self.assertIn(f"<td>#{result['ticket_id']}</td>", page)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                repo.close()


class TestRunCheck(unittest.TestCase):
    """`demo check` percorre o fluxo completo em ambiente descartável."""

    def test_todos_os_passos_passam(self):
        steps = run_check()
        falhas = [(s.label, s.detail) for s in steps if not s.ok]
        self.assertEqual(falhas, [])
        self.assertEqual(len(steps), 8)

    def test_nao_toca_no_banco_padrao_da_demo(self):
        # A checagem usa banco temporário: o demo.sqlite3 do diretório atual
        # não deve ser criado nem modificado.
        alvo = Path("demo.sqlite3")
        antes = alvo.stat().st_mtime_ns if alvo.exists() else None
        run_check()
        depois = alvo.stat().st_mtime_ns if alvo.exists() else None
        self.assertEqual(antes, depois)


class TestCliCheck(unittest.TestCase):
    """A saída do `demo check` deve ser legível: sem traceback, com veredito."""

    raiz = Path(__file__).resolve().parent.parent

    def _rodar(self, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "helpdesk.demo", "check"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(self.raiz), timeout=120, env=env,
        )

    def test_sucesso_sai_com_zero_e_resume(self):
        saida = self._rodar()
        self.assertEqual(saida.returncode, 0, saida.stdout + saida.stderr)
        self.assertIn("[ok]", saida.stdout)
        self.assertIn("Tudo certo", saida.stdout)
        self.assertNotIn("FALHOU", saida.stdout)

    def test_falha_aponta_o_passo_sem_traceback(self):
        # Quadro de atendentes configurado para um arquivo inexistente: a
        # checagem deve falhar nesse passo, com mensagem curta e código 1.
        env = {
            **os.environ,
            "HELPDESK_ATTENDANTS_PATH": str(self.raiz / "quadro-inexistente.json"),
        }
        saida = self._rodar(env=env)
        combinado = (saida.stdout or "") + (saida.stderr or "")
        self.assertEqual(saida.returncode, 1)
        self.assertIn("FALHOU", combinado)
        self.assertIn("quadro de atendentes", combinado)
        self.assertNotIn("Traceback", combinado)


class TestCliClear(unittest.TestCase):
    """`demo clear` esvazia o banco da demonstração (todos os chamados)."""

    raiz = Path(__file__).resolve().parent.parent

    def _rodar(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "helpdesk.demo", *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(self.raiz), timeout=60,
        )

    def test_clear_esvazia_o_banco(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = str(Path(tmpdir) / "demo-clear.sqlite3")
            seed = self._rodar("seed", "--db", db)
            self.assertEqual(seed.returncode, 0, seed.stdout + seed.stderr)

            repo = SqliteTicketRepository(db)
            try:
                self.assertGreater(len(repo.all()), 0)  # tem o que limpar
            finally:
                repo.close()

            limpar = self._rodar("clear", "--db", db)
            self.assertEqual(limpar.returncode, 0, limpar.stdout + limpar.stderr)
            self.assertIn("esvaziado", limpar.stdout)

            repo = SqliteTicketRepository(db)
            try:
                self.assertEqual(repo.all(), [])
                self.assertEqual(repo.next_id(), 1)  # ids recomeçam
            finally:
                repo.close()

    def test_clear_em_banco_inexistente_orienta_sem_traceback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = str(Path(tmpdir) / "nao-existe.sqlite3")
            saida = self._rodar("clear", "--db", db)
            combinado = (saida.stdout or "") + (saida.stderr or "")
            self.assertEqual(saida.returncode, 1)
            self.assertNotIn("Traceback", combinado)
            self.assertIn("não existe", combinado)


class TestCliLocate(unittest.TestCase):
    """`demo locate` define o local/modo de atendimento de um chamado."""

    raiz = Path(__file__).resolve().parent.parent

    def _rodar(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "helpdesk.demo", *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(self.raiz), timeout=60,
        )

    def test_locate_define_modo_e_local(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = str(Path(tmpdir) / "demo-locate.sqlite3")
            self.assertEqual(self._rodar("seed", "--db", db).returncode, 0)
            saida = self._rodar(
                "locate", "8", "--modo", "presencial", "--local", "Sala 9", "--db", db
            )
            self.assertEqual(saida.returncode, 0, saida.stdout + saida.stderr)

            repo = SqliteTicketRepository(db)
            try:
                t = repo.get(8)
                self.assertEqual(t.service_mode, ServiceMode.PRESENCIAL)
                self.assertEqual(t.location, "Sala 9")
            finally:
                repo.close()

    def test_locate_chamado_inexistente_sem_traceback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = str(Path(tmpdir) / "demo-locate2.sqlite3")
            self.assertEqual(self._rodar("seed", "--db", db).returncode, 0)
            saida = self._rodar("locate", "999", "--modo", "remoto", "--db", db)
            combinado = (saida.stdout or "") + (saida.stderr or "")
            self.assertEqual(saida.returncode, 1)
            self.assertNotIn("Traceback", combinado)
            self.assertIn("não encontrado", combinado)


class TestCliAmigavel(unittest.TestCase):
    """`demo send` nunca deve mostrar traceback bruto em uso normal."""

    def test_servidor_fora_do_ar_da_mensagem_curta(self):
        # Descobre uma porta livre (abre e fecha) — nada estará escutando nela.
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        porta_livre = probe.getsockname()[1]
        probe.close()

        raiz = Path(__file__).resolve().parent.parent
        saida = subprocess.run(
            [sys.executable, "-m", "helpdesk.demo", "send", "teste",
             "--port", str(porta_livre)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(raiz), timeout=30,
        )
        combinado = (saida.stdout or "") + (saida.stderr or "")
        self.assertEqual(saida.returncode, 1)
        self.assertNotIn("Traceback", combinado)
        self.assertIn("respondendo", combinado)   # "não está respondendo"
        self.assertIn("--port", combinado)        # orienta conferir a porta


if __name__ == "__main__":
    unittest.main()
