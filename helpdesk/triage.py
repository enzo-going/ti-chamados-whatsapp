"""Triagem automática: classifica o texto de uma mensagem em categoria e prioridade.

A abordagem é baseada em palavras-chave (rápida, transparente e sem dependências).
Foi deixada isolada de propósito: no futuro pode ser trocada por um classificador
de ML/NLP sem mexer no restante do sistema.
"""

from __future__ import annotations

import re
import unicodedata

from helpdesk.models import Category, Priority

# Palavras-chave por categoria. A ordem importa: a primeira categoria com
# alguma correspondência vence (categorias mais específicas vêm antes).
_CATEGORY_KEYWORDS: dict[Category, tuple[str, ...]] = {
    Category.REDE: (
        "rede", "internet", "wifi", "wi-fi", "sem conexao", "caiu a rede",
        "sem internet", "lan", "cabo de rede", "roteador", "switch",
    ),
    Category.IMPRESSORA: (
        "impressora", "imprimir", "impressao", "toner", "cartucho", "scanner",
    ),
    Category.ACESSO: (
        "senha", "login", "acesso", "bloqueado", "bloqueada", "email", "e-mail",
        "usuario", "conta", "permissao", "nao consigo entrar",
    ),
    # Solicitação/empréstimo de equipamento (ex.: notebook de apoio do setor de TI).
    # Vem ANTES de HARDWARE de propósito: "notebook" também é palavra de HARDWARE
    # (equipamento com defeito), então usamos frases específicas de solicitação
    # para que "preciso de um notebook" vença, enquanto "notebook nao liga" continua
    # em HARDWARE.
    Category.EMPRESTIMO_EQUIPAMENTO: (
        "preciso de um notebook", "preciso de notebook", "notebook emprestado",
        "emprestar notebook", "emprestimo de notebook", "emprestimo de equipamento",
        "reserva de notebook", "reservar notebook", "notebook para reuniao",
        "equipamento temporario", "pegar notebook", "notebook de apoio",
        "notebook de suporte",
    ),
    Category.HARDWARE: (
        "computador", "pc", "monitor", "teclado", "mouse", "nao liga",
        "desligou", "tela", "cabo", "fonte", "maquina", "notebook",
    ),
    Category.SOFTWARE: (
        "sistema", "programa", "software", "aplicativo", "erro", "travou",
        "travando", "lento", "atualizar", "instalar", "planilha", "excel",
    ),
}

# Sinais de alta prioridade (afeta várias pessoas ou serviço totalmente parado).
_HIGH_PRIORITY_SIGNALS: tuple[str, ...] = (
    "caiu", "parou", "fora do ar", "ninguem consegue", "todos", "urgente",
    "urgencia", "nada funciona", "sistema fora", "geral", "setor inteiro",
)

# Sinais de baixa prioridade (dúvida, sem urgência).
_LOW_PRIORITY_SIGNALS: tuple[str, ...] = (
    "duvida", "quando puder", "sem pressa", "como faco", "como faria",
    "gostaria de saber", "uma pergunta",
)


def _normalize(text: str) -> str:
    """Coloca em minúsculas e remove acentos para casar palavras-chave."""
    text = text.lower().strip()
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _matches(keyword: str, normalized_text: str) -> bool:
    """Casa a palavra-chave por palavra inteira, não por substring.

    Evita falsos positivos como "rede" dentro de "redefinir". Funciona também
    para palavras-chave compostas (ex.: "cabo de rede").
    """
    pattern = r"\b" + re.escape(_normalize(keyword)) + r"\b"
    return re.search(pattern, normalized_text) is not None


def classify_category(text: str) -> Category:
    """Retorna a categoria mais provável da mensagem."""
    normalized = _normalize(text)
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(_matches(k, normalized) for k in keywords):
            return category
    return Category.OUTROS


def classify_priority(text: str) -> Priority:
    """Estima a prioridade a partir de sinais de urgência no texto."""
    normalized = _normalize(text)
    if any(_matches(s, normalized) for s in _HIGH_PRIORITY_SIGNALS):
        return Priority.ALTA
    if any(_matches(s, normalized) for s in _LOW_PRIORITY_SIGNALS):
        return Priority.BAIXA
    return Priority.MEDIA


def make_subject(text: str, max_len: int = 60) -> str:
    """Gera um assunto curto a partir da primeira linha da mensagem."""
    first_line = text.strip().splitlines()[0] if text.strip() else "Sem descricao"
    if len(first_line) <= max_len:
        return first_line
    return first_line[: max_len - 1].rstrip() + "…"
