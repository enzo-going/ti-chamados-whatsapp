"""Testes do quadro de atendentes configurável (JSON local)."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpdesk import config
from helpdesk.attendants import (
    InvalidRoster,
    load_roster,
    load_roster_file,
    parse_roster,
)
from helpdesk.models import DEFAULT_ROLE


class TestParseRoster(unittest.TestCase):
    def test_quadro_completo(self):
        quadro = parse_roster(
            [
                {"id": "a1", "name": "Atendente 1", "role": "supervisor"},
                {"id": "a2", "name": "Atendente 2", "role": "efetivo", "active": False},
            ]
        )
        self.assertEqual(len(quadro), 2)
        self.assertEqual(quadro[0].role, "supervisor")
        self.assertTrue(quadro[0].active)
        self.assertEqual(quadro[1].role, "efetivo")
        self.assertFalse(quadro[1].active)

    def test_defaults_de_role_e_active(self):
        (atendente,) = parse_roster([{"id": "a1", "name": "Atendente 1"}])
        self.assertEqual(atendente.role, DEFAULT_ROLE)
        self.assertTrue(atendente.active)

    def test_normaliza_espacos(self):
        (atendente,) = parse_roster(
            [{"id": " a1 ", "name": " Atendente 1 ", "role": " efetivo "}]
        )
        self.assertEqual(atendente.id, "a1")
        self.assertEqual(atendente.name, "Atendente 1")
        self.assertEqual(atendente.role, "efetivo")

    def test_rejeita_nao_lista(self):
        with self.assertRaises(InvalidRoster):
            parse_roster({"id": "a1", "name": "Atendente 1"})

    def test_rejeita_quadro_vazio(self):
        with self.assertRaises(InvalidRoster):
            parse_roster([])

    def test_rejeita_entrada_nao_objeto(self):
        with self.assertRaises(InvalidRoster):
            parse_roster(["a1"])

    def test_rejeita_campos_obrigatorios_ausentes(self):
        with self.assertRaises(InvalidRoster):
            parse_roster([{"id": "a1"}])

    def test_rejeita_id_vazio(self):
        with self.assertRaises(InvalidRoster):
            parse_roster([{"id": "  ", "name": "Atendente 1"}])

    def test_rejeita_campo_desconhecido(self):
        # Um typo ("ativo" em vez de "active") deve falhar alto, não passar
        # silenciosamente deixando a pessoa no rodízio.
        with self.assertRaises(InvalidRoster):
            parse_roster([{"id": "a1", "name": "Atendente 1", "ativo": False}])

    def test_rejeita_id_duplicado(self):
        with self.assertRaises(InvalidRoster):
            parse_roster(
                [
                    {"id": "a1", "name": "Atendente 1"},
                    {"id": "a1", "name": "Atendente 1 de novo"},
                ]
            )

    def test_rejeita_active_nao_booleano(self):
        with self.assertRaises(InvalidRoster):
            parse_roster([{"id": "a1", "name": "Atendente 1", "active": "sim"}])

    def test_rejeita_role_vazio(self):
        with self.assertRaises(InvalidRoster):
            parse_roster([{"id": "a1", "name": "Atendente 1", "role": ""}])


class TestLoadRosterFile(unittest.TestCase):
    def _write(self, tmpdir: str, content: str) -> str:
        path = Path(tmpdir) / "atendentes.json"
        path.write_text(content, encoding="utf-8")
        return str(path)

    def test_carrega_arquivo_utf8(self):
        quadro = [{"id": "a1", "name": "Atendente São João", "role": "estagiário"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write(tmpdir, json.dumps(quadro, ensure_ascii=False))
            (atendente,) = load_roster_file(path)
        self.assertEqual(atendente.name, "Atendente São João")
        self.assertEqual(atendente.role, "estagiário")

    def test_json_invalido_e_erro_claro(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write(tmpdir, "{nao é json válido")
            with self.assertRaises(InvalidRoster) as ctx:
                load_roster_file(path)
        self.assertIn("JSON inválido", str(ctx.exception))


class TestLoadRoster(unittest.TestCase):
    def test_fallback_sem_configuracao(self):
        with mock.patch.dict(os.environ):
            os.environ.pop(config.ATTENDANTS_PATH_ENV, None)
            quadro = load_roster()
        self.assertTrue(quadro)  # exemplos genéricos para demo/testes
        self.assertTrue(any(a.active for a in quadro))
        self.assertTrue(all(a.role for a in quadro))
        # Repositório público: o fallback usa papéis genéricos, nunca nomes reais.
        for atendente in quadro:
            self.assertTrue(atendente.name.startswith("Atendente "))

    def test_usa_variavel_de_ambiente(self):
        quadro = [{"id": "env1", "name": "Atendente Env"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "quadro.json")
            Path(path).write_text(json.dumps(quadro), encoding="utf-8")
            with mock.patch.dict(os.environ, {config.ATTENDANTS_PATH_ENV: path}):
                (atendente,) = load_roster()
        self.assertEqual(atendente.id, "env1")

    def test_caminho_explicito_vence_variavel(self):
        no_env = [{"id": "env1", "name": "Atendente Env"}]
        explicito = [{"id": "arg1", "name": "Atendente Arg"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / "env.json"
            arg_path = Path(tmpdir) / "arg.json"
            env_path.write_text(json.dumps(no_env), encoding="utf-8")
            arg_path.write_text(json.dumps(explicito), encoding="utf-8")
            with mock.patch.dict(
                os.environ, {config.ATTENDANTS_PATH_ENV: str(env_path)}
            ):
                (atendente,) = load_roster(str(arg_path))
        self.assertEqual(atendente.id, "arg1")

    def test_arquivo_configurado_inexistente_e_erro(self):
        # Configuração explícita não cai silenciosamente no fallback.
        with self.assertRaises(FileNotFoundError):
            load_roster(os.path.join("nao", "existe", "quadro.json"))

    def test_exemplo_do_repositorio_e_valido(self):
        # O atendentes.exemplo.json versionado deve sempre carregar sem erro.
        raiz = Path(__file__).resolve().parent.parent
        quadro = load_roster_file(str(raiz / "atendentes.exemplo.json"))
        self.assertTrue(any(a.active for a in quadro))
        self.assertTrue(any(not a.active for a in quadro))  # demonstra inativo


if __name__ == "__main__":
    unittest.main()
