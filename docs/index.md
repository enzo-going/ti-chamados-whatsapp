---
tags: [helpdesk, documentacao]
---

# Documentação — ti-chamados-whatsapp

Índice da documentação do projeto: um núcleo de helpdesk de TI que organiza
chamados recebidos por WhatsApp em tickets, com triagem, atribuição e histórico.

## Documentos

- [Mapa do projeto](mapa.md) — visão de uma tela: fases e decisões por tema (ponto de partida).
- [Arquitetura](arquitetura.md) — visão de componentes, fluxo e ciclo de vida (com diagramas).
- [Roadmap](roadmap.md) — plano incremental por fases e decisões em aberto.
- [Registro de decisões](decisoes.md) — decisões de arquitetura (ADR).
- [Demonstração local](demo-local.md) — passo a passo para rodar e testar na máquina.
- [Roteiro de demonstração](roteiro-demo.md) — guia curto de apresentação (~10 min).
- [Checklist de pré-integração](pre-integracao.md) — o que validar antes de conectar uma linha real (sem credenciais no repositório).
- [Guia da Cloud API](guia-cloud-api.md) — passo a passo do dia: criar o app na Meta e validar com o número de teste.
- [Risco de banimento no WhatsApp](riscos-banimento.md) — por que o nosso uso (Cloud API oficial, reativo, interno) fica no lado de baixo risco, e como lidar com o que sobra.
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
| `helpdesk/whatsapp.py` | Borda da Cloud API: verificação do webhook, assinatura, parser e transporte de envio (HTTP injetável) |
| `helpdesk/http_app.py` | Servidor HTTP local (`127.0.0.1`): entrada + painel + rotas `/webhook` |
| `helpdesk/dashboard.py` | Painel somente leitura: projeção restrita + página HTML |
| `helpdesk/demo.py` | Demonstração: seed fake, simulação de mensagens e checagem automática (`check`) |
| `helpdesk/desktop.py` | Aplicativo Windows: ciclo de vida do servidor, dados persistentes e janela gráfica |
| `helpdesk/config.py` | Caminhos via variáveis de ambiente + checagem segura de configuração (`check`) |
| `main.py` | Demonstração de linha de comando (`--repl`, `--db`) |
| `desktop_app.py` | Ponto de entrada do executável Windows |
| `tests/` | Suíte de testes (unittest) |

## Status

- **Fase 1 — Persistência SQLite:** concluída (ver [roadmap](roadmap.md)).
- **Fase 2 — Entrada HTTP local + idempotência:** parte local entregue
  (payload neutro, idempotência, follow-up).
- **Fase 3 — Cloud API:** borda local entregue e testada sem rede
  (verificação do webhook, assinatura, parser, transporte injetável — ver
  [pre-integracao](pre-integracao.md)); a conexão real segue bloqueada pela
  decisão da estratégia do número.
- **Atendentes configuráveis:** entregue — quadro em JSON local com papéis e
  ativo/inativo (ver [decisões](decisoes.md), decisão 11).
- **Painel local somente leitura:** entregue — `/dashboard` com projeção
  restrita dos chamados em aberto, base do futuro wallboard (decisão 12).
- **Local/modo de atendimento + observabilidade:** chamados ganham local/modo
  (presencial/remoto; coluna no painel; comando `demo locate`), e a CLI e o log
  passam a relatar o desfecho da mensagem — criado/follow-up/reaberto
  (ver [decisões](decisoes.md), decisões 18–20).
- **Aplicativo Windows:** entregue — controlador local empacotável em `.exe`,
  com atalho na Área de Trabalho, banco persistente iniciado vazio e simulação
  opcional de mensagens (ver [demonstração](demo-local.md) e
  [decisões](decisoes.md), decisões 21–22).
