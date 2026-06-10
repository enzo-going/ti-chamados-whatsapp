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
- [Demonstração local](demo-local.md) — passo a passo para rodar e testar na máquina.
- [Roteiro de demonstração](roteiro-demo.md) — guia curto de apresentação (~10 min).
- [Visão geral (README)](../README.md) — descrição e instruções de uso.

## Mapa do código

| Módulo | Responsabilidade |
|---|---|
| `helpdesk/models.py` | Entidades de domínio (`Ticket`, `Message`, `Attendant`, enums) |
| `helpdesk/triage.py` | Classificação por palavras-chave (categoria + prioridade) |
| `helpdesk/attendants.py` | Quadro de atendentes configurável (JSON local: papéis, ativo/inativo) |
| `helpdesk/repository.py` | Armazenamento: em memória (testes/demo) + SQLite (persistente) |
| `helpdesk/transport.py` | Interface de envio + `FakeTransport` |
| `helpdesk/replies.py` | Mensagens automáticas (pt-BR) |
| `helpdesk/service.py` | Orquestra o fluxo completo |
| `helpdesk/inbound.py` | Camada de entrada: payload neutro → `Message`, com idempotência |
| `helpdesk/http_app.py` | Servidor HTTP local (`127.0.0.1`): entrada + painel |
| `helpdesk/dashboard.py` | Painel somente leitura: projeção restrita + página HTML |
| `helpdesk/demo.py` | Demonstração: seed de chamados fake + simulação de mensagens |
| `helpdesk/config.py` | Caminhos (banco, quadro de atendentes) via variáveis de ambiente |
| `main.py` | Demonstração de linha de comando (`--repl`, `--db`) |
| `tests/` | Suíte de testes (unittest) |

## Status

- **Fase 1 — Persistência SQLite:** concluída (ver [roadmap](roadmap.md)).
- **Fase 2 — Entrada HTTP local + idempotência:** parte local entregue
  (payload neutro, idempotência, follow-up); bordas reais aguardam a Fase 3.
- **Atendentes configuráveis:** entregue — quadro em JSON local com papéis e
  ativo/inativo (ver [decisões](decisoes.md), decisão 11).
- **Painel local somente leitura:** entregue — `/dashboard` com projeção
  restrita dos chamados em aberto, base do futuro wallboard (decisão 12).
