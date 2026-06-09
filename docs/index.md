---
tags: [helpdesk, documentacao]
---

# Documentação — ti-chamados-whatsapp

Índice da documentação do projeto: um núcleo de helpdesk de TI que organiza
chamados recebidos por WhatsApp em tickets, com triagem, atribuição e histórico.

## Documentos

- [Arquitetura](arquitetura.md) — visão de componentes, fluxo e ciclo de vida (com diagramas).
- [Roadmap](roadmap.md) — plano incremental por fases e decisões em aberto.
- [Registro de decisões](decisoes.md) — decisões de arquitetura (ADR).
- [Visão geral (README)](../README.md) — descrição e instruções de uso.

## Mapa do código

| Módulo | Responsabilidade |
|---|---|
| `helpdesk/models.py` | Entidades de domínio (`Ticket`, `Message`, `Attendant`, enums) |
| `helpdesk/triage.py` | Classificação por palavras-chave (categoria + prioridade) |
| `helpdesk/repository.py` | Armazenamento: em memória (testes/demo) + SQLite (persistente) |
| `helpdesk/transport.py` | Interface de envio + `FakeTransport` |
| `helpdesk/replies.py` | Mensagens automáticas (pt-BR) |
| `helpdesk/service.py` | Orquestra o fluxo completo |
| `helpdesk/config.py` | Caminho do banco via variável de ambiente |
| `main.py` | Demonstração de linha de comando (`--repl`, `--db`) |
| `tests/` | Suíte de testes (unittest) |

## Status

- **Fase 1 — Persistência SQLite:** concluída (ver [roadmap](roadmap.md)).
- **Fase 2 — Entrada HTTP:** próxima, aguardando início.
