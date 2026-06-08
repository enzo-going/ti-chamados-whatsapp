"""Testes da triagem (classificação de categoria e prioridade)."""

import unittest

from helpdesk.models import Category, Priority
from helpdesk.triage import classify_category, classify_priority, make_subject


class TestCategory(unittest.TestCase):
    def test_rede(self):
        self.assertEqual(classify_category("A rede caiu aqui no setor"), Category.REDE)
        self.assertEqual(classify_category("estou sem internet"), Category.REDE)

    def test_impressora(self):
        self.assertEqual(
            classify_category("a impressora não está imprimindo"), Category.IMPRESSORA
        )

    def test_acesso(self):
        self.assertEqual(classify_category("esqueci minha senha do email"), Category.ACESSO)

    def test_hardware(self):
        self.assertEqual(classify_category("meu computador não liga"), Category.HARDWARE)

    def test_software(self):
        self.assertEqual(classify_category("o sistema travou de novo"), Category.SOFTWARE)

    def test_outros_fallback(self):
        self.assertEqual(classify_category("bom dia, tudo bem?"), Category.OUTROS)

    def test_acentos_e_maiusculas(self):
        # Deve normalizar acentos e caixa.
        self.assertEqual(classify_category("SEM CONEXÃO de REDE"), Category.REDE)

    def test_nao_casa_substring(self):
        # "redefinir" contém "rede", mas não deve ser classificado como REDE.
        self.assertEqual(
            classify_category("esqueci minha senha do email, consigo redefinir?"),
            Category.ACESSO,
        )


class TestPriority(unittest.TestCase):
    def test_alta(self):
        self.assertEqual(classify_priority("a rede caiu, ninguem consegue trabalhar"), Priority.ALTA)
        self.assertEqual(classify_priority("URGENTE o sistema está fora do ar"), Priority.ALTA)

    def test_baixa(self):
        self.assertEqual(classify_priority("uma dúvida: como faço backup?"), Priority.BAIXA)

    def test_media_default(self):
        self.assertEqual(classify_priority("o mouse parou de funcionar"), Priority.ALTA)
        self.assertEqual(classify_priority("preciso instalar um programa"), Priority.MEDIA)


class TestSubject(unittest.TestCase):
    def test_curto(self):
        self.assertEqual(make_subject("rede caiu"), "rede caiu")

    def test_trunca_longo(self):
        texto = "x" * 100
        assunto = make_subject(texto, max_len=60)
        self.assertLessEqual(len(assunto), 60)

    def test_primeira_linha(self):
        self.assertEqual(make_subject("impressora travou\nno segundo andar"), "impressora travou")


if __name__ == "__main__":
    unittest.main()
