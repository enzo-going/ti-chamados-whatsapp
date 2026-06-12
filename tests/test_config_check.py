"""Testes da checagem segura de configuração (``helpdesk.config``).

O ponto central é a **não exposição de segredos**: a checagem reporta as
variáveis reservadas da integração apenas como definida/não definida — o valor
nunca pode aparecer na saída. Também garante que a checagem não tem efeitos
colaterais (não cria banco) e que os arquivos de salvaguarda do repositório
(.gitignore, .env.example) continuam protegendo dados sensíveis.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpdesk import config
from helpdesk.config import (
    ATTENDANTS_PATH_ENV,
    DB_PATH_ENV,
    INTEGRATION_ENV_VARS,
    ConfigStep,
    run_config_check,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

# Valor-sentinela: se aparecer em qualquer saída da checagem, há vazamento.
SENTINELA = "VALOR-SENSIVEL-NAO-PODE-APARECER-12345"


def _texto_completo(steps: list[ConfigStep]) -> str:
    return "\n".join(f"{step.label} {step.detail}" for step in steps)


class TestNaoExposicaoDeValores(unittest.TestCase):
    def test_valor_de_variavel_reservada_nunca_aparece(self):
        for name in INTEGRATION_ENV_VARS:
            with self.subTest(variavel=name):
                with mock.patch.dict(os.environ, {name: SENTINELA}):
                    saida = _texto_completo(run_config_check())
                self.assertNotIn(SENTINELA, saida)

    def test_variavel_reservada_definida_reporta_presenca(self):
        name = INTEGRATION_ENV_VARS[0]
        with mock.patch.dict(os.environ, {name: SENTINELA}):
            steps = run_config_check()
        (step,) = [s for s in steps if s.label == name]
        self.assertTrue(step.ok)
        self.assertIn("definida", step.detail)
        self.assertIn("valor não exibido", step.detail)

    def test_variavel_reservada_ausente_reporta_ausencia(self):
        name = INTEGRATION_ENV_VARS[0]
        env_sem_a_variavel = {k: v for k, v in os.environ.items() if k != name}
        with mock.patch.dict(os.environ, env_sem_a_variavel, clear=True):
            steps = run_config_check()
        (step,) = [s for s in steps if s.label == name]
        self.assertTrue(step.ok)
        self.assertIn("não definida", step.detail)

    def test_todas_as_variaveis_reservadas_entram_no_relatorio(self):
        labels = {step.label for step in run_config_check()}
        for name in INTEGRATION_ENV_VARS:
            self.assertIn(name, labels)


class TestChecagemSemEfeitosColaterais(unittest.TestCase):
    def test_checagem_nao_cria_o_banco(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "novo.sqlite3"
            with mock.patch.dict(os.environ, {DB_PATH_ENV: str(db)}):
                steps = run_config_check()
            (step,) = [s for s in steps if s.label == "banco SQLite"]
            self.assertTrue(step.ok)
            self.assertIn("será criado no primeiro uso", step.detail)
            self.assertFalse(db.exists(), "a checagem não pode criar o banco")

    def test_banco_existente_e_reportado_sem_ser_tocado(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "existente.sqlite3"
            db.write_bytes(b"conteudo-qualquer")
            antes = db.read_bytes()
            with mock.patch.dict(os.environ, {DB_PATH_ENV: str(db)}):
                steps = run_config_check()
            (step,) = [s for s in steps if s.label == "banco SQLite"]
            self.assertTrue(step.ok)
            self.assertIn("arquivo existe", step.detail)
            self.assertEqual(db.read_bytes(), antes)

    def test_diretorio_inexistente_falha_com_mensagem_clara(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "nao-existe" / "banco.sqlite3"
            with mock.patch.dict(os.environ, {DB_PATH_ENV: str(db)}):
                steps = run_config_check()
        (step,) = [s for s in steps if s.label == "banco SQLite"]
        self.assertFalse(step.ok)
        self.assertIn("não existe", step.detail)


class TestQuadroDeAtendentes(unittest.TestCase):
    def test_sem_configuracao_usa_o_quadro_de_exemplo(self):
        env_limpo = {
            k: v for k, v in os.environ.items() if k != ATTENDANTS_PATH_ENV
        }
        with mock.patch.dict(os.environ, env_limpo, clear=True):
            steps = run_config_check()
        (step,) = [s for s in steps if s.label == "quadro de atendentes"]
        self.assertTrue(step.ok)
        self.assertIn("quadro de exemplo", step.detail)

    def test_arquivo_invalido_falha(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            quadro = Path(tmpdir) / "quadro.json"
            quadro.write_text("{isto não é json válido", encoding="utf-8")
            with mock.patch.dict(
                os.environ, {ATTENDANTS_PATH_ENV: str(quadro)}
            ):
                steps = run_config_check()
        (step,) = [s for s in steps if s.label == "quadro de atendentes"]
        self.assertFalse(step.ok)


class TestSalvaguardasDoRepositorio(unittest.TestCase):
    """O repositório é público: estes arquivos seguram dados sensíveis fora."""

    def test_gitignore_cobre_arquivos_sensiveis(self):
        linhas = (
            (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        )
        regras = {linha.strip() for linha in linhas}
        for obrigatoria in (".env", "atendentes.json", "*.sqlite3"):
            self.assertIn(
                obrigatoria,
                regras,
                f"a regra {obrigatoria!r} precisa continuar no .gitignore",
            )

    def test_env_example_tem_somente_nomes_sem_valores(self):
        linhas = (
            (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        )
        atribuicoes = [
            linha.strip()
            for linha in linhas
            if linha.strip() and not linha.strip().startswith("#")
        ]
        self.assertTrue(atribuicoes, "o .env.example deve listar variáveis")
        for linha in atribuicoes:
            nome, separador, valor = linha.partition("=")
            self.assertEqual(separador, "=", f"linha inesperada: {linha!r}")
            self.assertEqual(
                valor.strip(),
                "",
                f"{nome} não pode ter valor preenchido no .env.example",
            )

    def test_env_example_documenta_as_variaveis_conhecidas(self):
        conteudo = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        for name in (DB_PATH_ENV, ATTENDANTS_PATH_ENV, *INTEGRATION_ENV_VARS):
            self.assertIn(f"{name}=", conteudo)


class TestRelatorioCompleto(unittest.TestCase):
    def test_checagem_padrao_passa_nesta_maquina(self):
        # Sem variáveis sensíveis definidas, a checagem deve ficar toda ok
        # (banco padrão no diretório atual + quadro de exemplo).
        env_limpo = {
            k: v
            for k, v in os.environ.items()
            if k not in {DB_PATH_ENV, ATTENDANTS_PATH_ENV, *INTEGRATION_ENV_VARS}
        }
        with mock.patch.dict(os.environ, env_limpo, clear=True):
            steps = run_config_check()
        self.assertTrue(all(step.ok for step in steps), steps)

    def test_saida_impressa_nao_vaza_valores(self):
        # Exercita a saída de terminal de verdade: com uma variável sensível
        # definida, o texto impresso reporta presença mas nunca o valor.
        import argparse
        import contextlib
        import io

        buffer = io.StringIO()
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in {DB_PATH_ENV, ATTENDANTS_PATH_ENV}
        }
        env[INTEGRATION_ENV_VARS[0]] = SENTINELA
        with mock.patch.dict(
            os.environ, env, clear=True
        ), contextlib.redirect_stdout(buffer):
            config._cmd_check(argparse.Namespace())
        saida = buffer.getvalue()
        self.assertIn(INTEGRATION_ENV_VARS[0], saida)
        self.assertIn("valor não exibido", saida)
        self.assertNotIn(SENTINELA, saida)


if __name__ == "__main__":
    unittest.main()
