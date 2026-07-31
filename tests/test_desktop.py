import json
import os
from pathlib import Path
import tempfile
import unittest
import urllib.request

from helpdesk.desktop import (
    DATABASE_FILE_NAME,
    DesktopServer,
    _SingleInstanceGuard,
    run_smoke_test,
)


class DesktopServerTests(unittest.TestCase):
    def test_primeira_execucao_popula_e_serve_a_demonstracao(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = DesktopServer(Path(temp_dir))
            self.assertTrue(server.seeded_on_start)
            self.assertEqual(6, server.open_ticket_count())

            try:
                server.start()
                with urllib.request.urlopen(
                    f"{server.base_url}/health", timeout=5
                ) as response:
                    health = json.loads(response.read())
                self.assertEqual("ok", health["status"])

                with urllib.request.urlopen(server.dashboard_url, timeout=5) as response:
                    dashboard = response.read().decode("utf-8")
                self.assertIn("Chamados em aberto", dashboard)

                result = server.simulate_message("a impressora do setor parou")
                self.assertEqual("criado", result["outcome"])
                self.assertEqual(7, server.open_ticket_count())
            finally:
                server.stop()

            self.assertTrue((Path(temp_dir) / DATABASE_FILE_NAME).is_file())

    def test_reabertura_preserva_o_banco_existente(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_directory = Path(temp_dir)
            first = DesktopServer(data_directory)
            try:
                self.assertTrue(first.seeded_on_start)
                original_count = len(first.repository.all())
            finally:
                first.stop()

            second = DesktopServer(data_directory)
            try:
                self.assertFalse(second.seeded_on_start)
                self.assertEqual(original_count, len(second.repository.all()))
            finally:
                second.stop()

    def test_stop_pode_ser_chamado_mais_de_uma_vez(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = DesktopServer(Path(temp_dir))
            server.start()
            server.stop()
            server.stop()

    def test_smoke_test_isolado(self):
        run_smoke_test()

    @unittest.skipUnless(os.name == "nt", "mutex exclusivo do Windows")
    def test_mutex_detecta_segunda_instancia(self):
        first = _SingleInstanceGuard()
        second = _SingleInstanceGuard()
        try:
            first.acquire()
            self.assertFalse(first.already_running)
            second.acquire()
            self.assertTrue(second.already_running)
        finally:
            second.release()
            first.release()


if __name__ == "__main__":
    unittest.main()
